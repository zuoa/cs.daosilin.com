"""Validated, reusable public feedback intake."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from itsdangerous import BadSignature, URLSafeSerializer
from peewee import fn

from database import FeedbackSubmission


COOKIE_NAME = 'cs_feedback_visitor'
COOKIE_MAX_AGE = 365 * 24 * 60 * 60
VISITOR_SALT = 'public-feedback-visitor'
HOURLY_LIMIT = 5
DUPLICATE_WINDOW_MINUTES = 10

# Adding another feedback surface means registering its type here and mapping
# its page-specific copy to the common subject/content/details contract.
FEEDBACK_TYPES = {
    'award_suggestion': {
        'label': '奖项建议',
        'context_types': {'season'},
    },
}
FEEDBACK_STATUSES = {'new', 'reviewing', 'replied', 'closed'}


class FeedbackError(ValueError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _clean_text(
    value: object,
    label: str,
    maximum: int,
    *,
    required: bool = False,
    single_line: bool = False,
) -> str:
    if value is None:
        value = ''
    if not isinstance(value, str):
        raise FeedbackError(f'{label}格式无效')
    text = value.replace('\r\n', '\n').replace('\r', '\n').strip()
    if single_line:
        text = re.sub(r'\s+', ' ', text)
    if required and not text:
        raise FeedbackError(f'{label}不能为空')
    if len(text) > maximum:
        raise FeedbackError(f'{label}不能超过 {maximum} 个字')
    return text


def _json_object(value: object, label: str, maximum: int) -> tuple[dict[str, Any], str]:
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise FeedbackError(f'{label}格式无效')
    try:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    except (TypeError, ValueError):
        raise FeedbackError(f'{label}必须是可序列化的对象') from None
    if len(serialized) > maximum:
        raise FeedbackError(f'{label}内容过长')
    return value, serialized


def normalize_feedback(data: object) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise FeedbackError('反馈内容格式无效')
    feedback_type = _clean_text(
        data.get('type'), '反馈类型', 48, required=True, single_line=True,
    )
    spec = FEEDBACK_TYPES.get(feedback_type)
    if not spec:
        raise FeedbackError('暂不支持这种反馈类型')

    subject = _clean_text(
        data.get('subject'), '主题', 120, required=True, single_line=True,
    )
    content = _clean_text(data.get('content'), '反馈内容', 800, required=True)
    submitter_name = _clean_text(
        data.get('submitter_name'), '署名', 64, single_line=True,
    )
    source_path = _clean_text(
        data.get('source_path'), '来源页面', 500, single_line=True,
    )
    if source_path:
        parsed = urlsplit(source_path)
        source_path = parsed.path if source_path.startswith('/') else ''

    context, context_json = _json_object(data.get('context'), '反馈上下文', 1500)
    context_type = _clean_text(
        context.get('type'), '上下文类型', 48, single_line=True,
    )
    context_id = _clean_text(
        context.get('id'), '上下文标识', 128, single_line=True,
    )
    if context_type not in spec['context_types']:
        raise FeedbackError('反馈上下文与类型不匹配')
    if not context_id:
        raise FeedbackError('上下文标识不能为空')

    _, details_json = _json_object(data.get('details'), '补充信息', 2500)
    return {
        'feedback_type': feedback_type,
        'subject': subject,
        'content': content,
        'submitter_name': submitter_name or None,
        'context_type': context_type,
        'context_id': context_id,
        'context_json': context_json,
        'details_json': details_json,
        'source_path': source_path or None,
    }


def read_visitor_id(secret_key: str, token: str | None) -> str | None:
    if not token:
        return None
    try:
        visitor_id = URLSafeSerializer(secret_key, salt=VISITOR_SALT).loads(token)
    except BadSignature:
        return None
    if not isinstance(visitor_id, str) or not 16 <= len(visitor_id) <= 128:
        return None
    return visitor_id


def new_visitor(secret_key: str) -> tuple[str, str]:
    visitor_id = secrets.token_urlsafe(32)
    token = URLSafeSerializer(secret_key, salt=VISITOR_SALT).dumps(visitor_id)
    return visitor_id, token


def visitor_fingerprint(secret_key: str, visitor_id: str) -> str:
    return hmac.new(
        str(secret_key).encode('utf-8'),
        visitor_id.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def _submission_key(values: dict[str, Any], fingerprint: str) -> str:
    stable = '|'.join((
        fingerprint,
        values['feedback_type'],
        values['context_type'],
        values['context_id'],
        values['subject'].casefold(),
        values['content'],
        values['details_json'],
    ))
    return hashlib.sha256(stable.encode('utf-8')).hexdigest()


def submit_feedback(
    data: object,
    fingerprint: str,
    *,
    now: datetime | None = None,
) -> tuple[FeedbackSubmission, bool]:
    values = normalize_feedback(data)
    now = now or datetime.now()
    submission_key = _submission_key(values, fingerprint)
    duplicate = (FeedbackSubmission.select()
                 .where(
                     FeedbackSubmission.submission_key == submission_key,
                     FeedbackSubmission.created_at >= now - timedelta(
                         minutes=DUPLICATE_WINDOW_MINUTES,
                     ),
                 )
                 .order_by(FeedbackSubmission.created_at.desc())
                 .first())
    if duplicate:
        return duplicate, True

    recent_count = (FeedbackSubmission.select()
                    .where(
                        FeedbackSubmission.fingerprint == fingerprint,
                        FeedbackSubmission.created_at >= now - timedelta(hours=1),
                    )
                    .count())
    if recent_count >= HOURLY_LIMIT:
        raise FeedbackError('提交得有点快，请一小时后再试', 429)

    row = FeedbackSubmission.create(
        public_id=f'fb_{secrets.token_hex(8)}',
        fingerprint=fingerprint,
        submission_key=submission_key,
        created_at=now,
        updated_at=now,
        **values,
    )
    return row, False


def public_feedback_payload(row: FeedbackSubmission, duplicate: bool = False) -> dict[str, Any]:
    return {
        'reference': row.public_id,
        'type': row.feedback_type,
        'subject': row.subject,
        'status': row.status,
        'reply': row.reply_content,
        'replied_at': row.replied_at.isoformat(timespec='seconds') if row.replied_at else None,
        'created_at': row.created_at.isoformat(timespec='seconds'),
        'duplicate': duplicate,
    }


def get_public_feedback(reference: str, fingerprint: str) -> FeedbackSubmission | None:
    reference = _clean_text(reference, '反馈编号', 32, single_line=True)
    if not reference:
        return None
    return FeedbackSubmission.get_or_none(
        FeedbackSubmission.public_id == reference,
        FeedbackSubmission.fingerprint == fingerprint,
    )


def _decode_object(value: str | None) -> dict[str, Any]:
    try:
        result = json.loads(value or '{}')
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def admin_feedback_payload(row: FeedbackSubmission) -> dict[str, Any]:
    return {
        'reference': row.public_id,
        'type': row.feedback_type,
        'type_label': (FEEDBACK_TYPES.get(row.feedback_type) or {}).get('label', row.feedback_type),
        'subject': row.subject,
        'content': row.content,
        'submitter_name': row.submitter_name,
        'context_type': row.context_type,
        'context_id': row.context_id,
        'context': _decode_object(row.context_json),
        'details': _decode_object(row.details_json),
        'source_path': row.source_path,
        'status': row.status,
        'reply': row.reply_content,
        'replied_by': row.replied_by,
        'replied_at': row.replied_at.isoformat(timespec='seconds') if row.replied_at else None,
        'created_at': row.created_at.isoformat(timespec='seconds'),
        'updated_at': row.updated_at.isoformat(timespec='seconds'),
    }


def feedback_inbox(
    *,
    feedback_type: str = '',
    status: str = '',
    query_text: str = '',
    page: int = 1,
    page_size: int = 40,
) -> dict[str, Any]:
    query = FeedbackSubmission.select()
    if feedback_type:
        if feedback_type not in FEEDBACK_TYPES:
            raise FeedbackError('反馈类型无效')
        query = query.where(FeedbackSubmission.feedback_type == feedback_type)
    if status:
        if status not in FEEDBACK_STATUSES:
            raise FeedbackError('反馈状态无效')
        query = query.where(FeedbackSubmission.status == status)
    query_text = _clean_text(query_text, '搜索内容', 80, single_line=True)
    if query_text:
        pattern = f'%{query_text}%'
        query = query.where(
            (FeedbackSubmission.subject ** pattern)
            | (FeedbackSubmission.content ** pattern)
            | (FeedbackSubmission.submitter_name ** pattern)
        )
    total = query.count()
    rows = list(query.order_by(FeedbackSubmission.created_at.desc())
                .paginate(page, page_size))
    counts = {
        row.status: int(row.count or 0)
        for row in (FeedbackSubmission
                    .select(FeedbackSubmission.status,
                            fn.COUNT(FeedbackSubmission.id).alias('count'))
                    .group_by(FeedbackSubmission.status))
    }
    return {
        'items': [admin_feedback_payload(row) for row in rows],
        'total': total,
        'page': page,
        'page_size': page_size,
        'counts': {key: counts.get(key, 0) for key in FEEDBACK_STATUSES},
        'types': [
            {'key': key, 'label': spec['label']}
            for key, spec in FEEDBACK_TYPES.items()
        ],
    }


def update_feedback(
    reference: str,
    data: object,
    admin_name: str,
    *,
    now: datetime | None = None,
) -> FeedbackSubmission | None:
    if not isinstance(data, dict):
        raise FeedbackError('更新内容格式无效')
    row = FeedbackSubmission.get_or_none(FeedbackSubmission.public_id == reference)
    if not row:
        return None
    now = now or datetime.now()
    status = _clean_text(data.get('status'), '反馈状态', 24, single_line=True)
    if status and status not in FEEDBACK_STATUSES:
        raise FeedbackError('反馈状态无效')
    if 'reply' in data:
        reply = _clean_text(data.get('reply'), '回复内容', 1200)
        row.reply_content = reply or None
        row.replied_at = now if reply else None
        row.replied_by = admin_name if reply else None
        if reply and not status:
            status = 'replied'
    if status:
        row.status = status
    row.updated_at = now
    row.save()
    return row
