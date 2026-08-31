"""RQ producer and worker job for Perfect World Arena demo analysis."""
import bz2
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

import requests
import zstandard

from ajlog import logger
from cache_service import invalidate_season
from config import (DEMO_ANALYZER_PATH, DEMO_ANALYZER_TIMEOUT, DEMO_BACKFILL_DAYS,
                    DEMO_MAX_BYTES, DEMO_METRIC_VERSION, DEMO_STORAGE_PATH,
                    REDIS_URL)
from database import DemoAnalysis, DemoCredential, Match, db
from demo_service import (PARSER_NAME, PARSER_VERSION, demo_analysis_enabled,
                          has_demo_credential, load_demo_credential,
                          persist_analysis)


class DemoUnavailable(Exception):
    pass


def _safe_error(exc, secrets=()):
    message = str(exc)
    for secret in secrets:
        if secret:
            message = message.replace(str(secret), '[REDACTED]')
    sensitive_query_keys = (
        'access_token|signature|ossaccesskeyid|x-oss-signature|'
        'x-oss-credential|x-oss-security-token'
    )
    message = re.sub(
        rf'(?i)((?:[?&])(?:{sensitive_query_keys})=)[^&\s]+',
        r'\1[REDACTED]',
        message,
    )
    return message[:2000]


def _state(match_id, status, **values):
    row, _ = DemoAnalysis.get_or_create(
        match_id=match_id,
        defaults={'source_match_id': match_id.removeprefix('PVP@'),
                  'metric_version': DEMO_METRIC_VERSION},
    )
    row.status = status
    row.metric_version = DEMO_METRIC_VERSION
    for key, value in values.items():
        setattr(row, key, value)
    row.save()
    match = Match.get_or_none(Match.match_id == match_id)
    if match and match.cup_name:
        invalidate_season(match.cup_name, external=False)
    return row


def _queue():
    if not REDIS_URL:
        return None
    from redis import Redis
    from rq import Queue
    from rq.serializers import JSONSerializer
    return Queue('demo-analysis', connection=Redis.from_url(REDIS_URL),
                 serializer=JSONSerializer, default_timeout=DEMO_ANALYZER_TIMEOUT + 60)


def _demo_job_id(row_id, match_id, metric_version):
    """Build an RQ-compatible ID without leaking arbitrary match ID characters."""
    identity = f'{match_id}\0{metric_version}'.encode('utf-8')
    return f'demo-analysis-{row_id}-{hashlib.sha256(identity).hexdigest()[:16]}'


def schedule_demo_analysis(match_id: str, force=False):
    """Create durable state first, then best-effort enqueue an idempotent RQ job."""
    row, _ = DemoAnalysis.get_or_create(
        match_id=match_id,
        defaults={'source_match_id': match_id.removeprefix('PVP@'),
                  'metric_version': DEMO_METRIC_VERSION},
    )
    if not demo_analysis_enabled():
        return row
    if row.status == 'completed' and row.metric_version == DEMO_METRIC_VERSION and not force:
        return row
    if not has_demo_credential():
        return _state(match_id, 'blocked_credentials', error_code='credentials_missing',
                      error_message='尚未配置 PWA Demo 凭证', next_retry_at=None)
    queue = _queue()
    if queue is None:
        return _state(match_id, 'pending', error_code='redis_unavailable',
                      error_message='REDIS_URL 未配置')
    job_id = _demo_job_id(row.id, match_id, DEMO_METRIC_VERSION)
    existing = queue.fetch_job(job_id)
    if existing:
        existing_status = existing.get_status(refresh=True)
        if existing_status == 'started':
            return row
        if not force and existing_status in ('queued', 'deferred', 'scheduled'):
            return row
        try:
            # A manual retry must replace an interval-based retry in
            # ScheduledJobRegistry instead of silently waiting for it.
            if existing_status in ('queued', 'deferred', 'scheduled'):
                existing.cancel()
            existing.delete()
        except Exception as exc:
            raise RuntimeError('无法清理已有 Demo 队列任务，请稍后重试') from exc
    from rq import Retry
    queue.enqueue(
        run_demo_analysis,
        match_id,
        job_id=job_id,
        retry=Retry(max=3, interval=[60, 600, 3600]),
        job_timeout=DEMO_ANALYZER_TIMEOUT + 60,
        result_ttl=86400,
        failure_ttl=7 * 86400,
    )
    return _state(match_id, 'queued', queued_at=datetime.now(), error_code=None,
                  error_message=None, next_retry_at=None)


def reconcile_demo_jobs(days=None):
    """Backfill recent matches and recover pending or stale queue states."""
    if not demo_analysis_enabled():
        return {'eligible': 0, 'scheduled': 0, 'disabled': True}
    cutoff = datetime.now() - timedelta(days=days or DEMO_BACKFILL_DAYS)
    matches = Match.select(Match.match_id).where(Match.end_time >= cutoff)
    scheduled = 0
    for match in matches:
        row = DemoAnalysis.get_or_none(DemoAnalysis.match_id == match.match_id)
        stale = bool(row and row.status in ('queued', 'downloading', 'validating', 'parsing')
                     and row.updated_at < datetime.now() - timedelta(minutes=30))
        if row and row.status in ('completed', 'unavailable') and row.metric_version == DEMO_METRIC_VERSION:
            continue
        # RQ owns the bounded automatic retries. Reconciliation must not turn
        # a permanently failed job into an unbounded retry loop.
        if (row and row.status == 'failed' and
                row.metric_version == DEMO_METRIC_VERSION):
            continue
        schedule_demo_analysis(match.match_id, force=stale)
        scheduled += 1
    return {'eligible': matches.count(), 'scheduled': scheduled, 'disabled': False}


def _write_bounded(response, destination: Path):
    declared = int(response.headers.get('Content-Length') or 0)
    if declared > DEMO_MAX_BYTES:
        raise ValueError('Demo 文件超过 1 GiB 限制')
    size = 0
    with destination.open('wb') as output:
        for chunk in response.iter_content(1024 * 1024):
            if not chunk:
                continue
            size += len(chunk)
            if size > DEMO_MAX_BYTES:
                raise ValueError('Demo 文件超过 1 GiB 限制')
            output.write(chunk)
    return size


def _copy_bounded(source, target):
    total = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            return total
        total += len(chunk)
        if total > DEMO_MAX_BYTES:
            raise ValueError('解压后的 Demo 超过 1 GiB 限制')
        target.write(chunk)


def _extract_demo(download_path: Path, demo_path: Path):
    is_zip = zipfile.is_zipfile(download_path)
    is_bzip = False
    if is_zip:
        with zipfile.ZipFile(download_path) as archive:
            candidates = [item for item in archive.infolist()
                          if not item.is_dir() and item.filename.lower().endswith('.dem')]
            if not candidates:
                raise ValueError('下载压缩包内没有 .dem 文件')
            item = candidates[0]
            if item.file_size > DEMO_MAX_BYTES:
                raise ValueError('解压后的 Demo 超过 1 GiB 限制')
            with archive.open(item) as source, demo_path.open('wb') as target:
                _copy_bounded(source, target)
    else:
        with download_path.open('rb') as source:
            is_bzip = source.read(3) == b'BZh'
    if is_bzip:
        with bz2.open(download_path, 'rb') as source, demo_path.open('wb') as target:
            _copy_bounded(source, target)
    elif not is_zip:
        shutil.copyfile(download_path, demo_path)
    with demo_path.open('rb') as source:
        if not source.read(8).startswith(b'PBDEMS2'):
            raise ValueError('文件不是有效的 CS2 Demo（缺少 PBDEMS2 header）')


def _download_demo(match_id: str, credential: dict, temp_dir: Path):
    try:
        from cs_demo_downloader.core.downloader_pwa import build_download_headers, get_demo_url
    except ImportError as exc:
        raise RuntimeError('cs-demo-downloader 未安装') from exc
    source_id = match_id.removeprefix('PVP@')
    try:
        url = get_demo_url(source_id, credential['access_token'])
    except Exception as exc:
        message = str(exc).lower()
        if any(word in message for word in ('not found', '不存在', 'expired', '过期')):
            raise DemoUnavailable('上游未提供或已过期') from exc
        raise
    if not url:
        raise DemoUnavailable('上游未提供 Demo 下载地址')
    headers = build_download_headers(credential['steam_id'])
    try:
        response = requests.get(url, headers=headers, stream=True, timeout=(15, 120))
        if response.status_code in (404, 410):
            raise DemoUnavailable('上游 Demo 不存在或已过期')
        if response.status_code in (401, 403):
            raise PermissionError('PWA 凭证已失效')
        if response.status_code >= 400:
            raise RuntimeError(f'PWA Demo 下载返回 HTTP {response.status_code}')
        path = temp_dir / 'download.bin'
        _write_bounded(response, path)
    finally:
        if 'response' in locals():
            response.close()
    demo_path = temp_dir / 'match.dem'
    _extract_demo(path, demo_path)
    return demo_path


def _analyse(demo_path: Path):
    completed = subprocess.run(
        [DEMO_ANALYZER_PATH, '--demo', str(demo_path), '--timeout', f'{DEMO_ANALYZER_TIMEOUT}s'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        timeout=DEMO_ANALYZER_TIMEOUT + 10, check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or 'Demo parser failed').strip()[-1000:]
        raise ValueError(detail)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError('Demo parser 返回了无效 JSON') from exc


def _compress_file(source: Path, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    compressor = zstandard.ZstdCompressor(level=10)
    with source.open('rb') as src, temporary.open('wb') as dst:
        compressor.copy_stream(src, dst)
    os.replace(temporary, destination)


def _compress_json(payload: dict, destination: Path):
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode()
    compressed = zstandard.ZstdCompressor(level=10).compress(encoded)
    temporary = destination.with_suffix(destination.suffix + '.tmp')
    temporary.write_bytes(compressed)
    os.replace(temporary, destination)


def run_demo_analysis(match_id: str):
    """Download, validate, parse and atomically publish one match analysis."""
    if db.is_closed():
        db.connect(reuse_if_open=True)
    if not demo_analysis_enabled():
        row = _state(match_id, 'pending', error_code='analysis_disabled',
                     error_message='Demo 分析已在管理后台关闭', next_retry_at=None)
        return {'status': row.status, 'disabled': True}
    row = _state(match_id, 'downloading', started_at=datetime.now(), heartbeat_at=datetime.now(),
                 attempt_count=(DemoAnalysis.get(DemoAnalysis.match_id == match_id).attempt_count or 0) + 1,
                 error_code=None, error_message=None, finished_at=None, next_retry_at=None)
    try:
        credential = load_demo_credential()
        if not credential:
            _state(match_id, 'blocked_credentials', error_code='credentials_missing',
                   error_message='尚未配置 PWA Demo 凭证', next_retry_at=None)
            return {'status': 'blocked_credentials'}
        storage = Path(DEMO_STORAGE_PATH)
        (storage / 'tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='demo-', dir=str(storage / 'tmp')) as temp_name:
            temp_dir = Path(temp_name)
            demo_path = _download_demo(match_id, credential, temp_dir)
            _state(match_id, 'validating', heartbeat_at=datetime.now())
            digest = hashlib.sha256()
            with demo_path.open('rb') as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b''):
                    digest.update(chunk)
            sha256 = digest.hexdigest()
            size = demo_path.stat().st_size
            _state(match_id, 'parsing', heartbeat_at=datetime.now(), demo_sha256=sha256,
                   demo_size=size)
            payload = _analyse(demo_path)
            match = Match.get_or_none(Match.match_id == match_id)
            parsed_map = str((payload.get('map_data') or {}).get('map_name') or '').lower()
            expected_map = str(match.map_name_en or match.map_name or '').lower() if match else ''
            normalize = lambda value: value.removeprefix('de_').replace(' ', '').replace('_', '')
            if expected_map and parsed_map and normalize(expected_map) != normalize(parsed_map):
                raise ValueError(f'Demo 地图 {parsed_map} 与比赛 {expected_map} 不一致')
            player_count = persist_analysis(match_id, payload)
            content_dir = storage / sha256[:2] / sha256
            demo_archive = content_dir / 'match.dem.zst'
            result_archive = content_dir / f'analysis-{DEMO_METRIC_VERSION}.json.zst'
            _compress_file(demo_path, demo_archive)
            _compress_json(payload, result_archive)
        _state(match_id, 'completed', demo_sha256=sha256, demo_size=size,
               archive_path=str(demo_archive), raw_result_path=str(result_archive),
               parser_name=PARSER_NAME, parser_version=PARSER_VERSION,
               finished_at=datetime.now(), heartbeat_at=datetime.now(), next_retry_at=None)
        credential_row = DemoCredential.get_or_none(DemoCredential.source == 'pwa')
        if credential_row:
            credential_row.last_validated_at = datetime.now()
            credential_row.last_error = None
            credential_row.save()
        return {'status': 'completed', 'players': player_count, 'sha256': sha256}
    except DemoUnavailable as exc:
        _state(match_id, 'unavailable', error_code='demo_unavailable', error_message=str(exc),
               finished_at=datetime.now(), next_retry_at=None)
        return {'status': 'unavailable'}
    except PermissionError as exc:
        _state(match_id, 'blocked_credentials', error_code='credentials_invalid',
               error_message=str(exc), finished_at=datetime.now(), next_retry_at=None)
        credential_row = DemoCredential.get_or_none(DemoCredential.source == 'pwa')
        if credential_row:
            credential_row.last_error = str(exc)
            credential_row.save()
        return {'status': 'blocked_credentials'}
    except Exception as exc:
        secret = credential.get('access_token') if 'credential' in locals() and credential else ''
        safe_message = _safe_error(exc, (secret,))
        logger.error(f'Demo 分析失败 match={match_id} type={type(exc).__name__}: {safe_message}')
        attempt = row.attempt_count or 1
        retry_delay = (60, 600, 3600)[min(attempt - 1, 2)]
        try:
            from rq import get_current_job
            current_job = get_current_job()
            will_retry = bool(current_job and current_job.retries_left > 0)
        except Exception:
            will_retry = False
        _state(match_id, 'failed', error_code=type(exc).__name__.lower(),
               error_message=safe_message, finished_at=datetime.now(),
               next_retry_at=(datetime.now() + timedelta(seconds=retry_delay)
                              if will_retry else None))
        raise
