"""RQ producer and worker jobs for DeepSeek player season summaries."""
import json
import re
from datetime import datetime

from ajlog import logger
from config import (LLM_API_KEY, LLM_MODEL_NAME, PLAYER_SUMMARY_PROMPT_VERSION,
                    REDIS_URL)
from database import MatchPlayer, PlayerSeasonSummary, Season
from player_summary_service import (build_summary_input, generate_summary,
                                    llm_configured, snapshot_hash)


def _safe_error(exc):
    message = str(exc)
    if LLM_API_KEY:
        message = message.replace(LLM_API_KEY, '[REDACTED]')
    message = re.sub(r'(?i)(authorization:\s*bearer\s+)[^\s]+', r'\1[REDACTED]', message)
    return message[:2000]


def _queue():
    if not REDIS_URL:
        return None
    from redis import Redis
    from rq import Queue
    from rq.serializers import JSONSerializer
    return Queue('player-summary', connection=Redis.from_url(REDIS_URL),
                 serializer=JSONSerializer, default_timeout=120)


def _row(cup_name, player_id):
    row, _ = PlayerSeasonSummary.get_or_create(
        cup_name=cup_name,
        player_id=player_id,
        defaults={'status': 'pending'},
    )
    return row


def _player_summary_job_id(summary_id, digest):
    """Build an RQ-compatible, deterministic ID for one summary snapshot."""
    return f'player-summary-{summary_id}-{digest[:16]}'


def schedule_player_summary(cup_name, player_id, force=False, snapshot=None):
    """Persist intent first and idempotently enqueue a summary generation."""
    snapshot = snapshot or build_summary_input(cup_name, player_id)
    if not snapshot:
        return None, False
    digest = snapshot_hash(snapshot)
    row = _row(cup_name, player_id)
    if (not force and row.status == 'completed' and row.source_hash == digest and
            row.prompt_version == PLAYER_SUMMARY_PROMPT_VERSION and
            row.model_name == LLM_MODEL_NAME):
        return row, False
    if (not force and row.status == 'failed' and row.requested_hash == digest and
            row.prompt_version == PLAYER_SUMMARY_PROMPT_VERSION and
            row.model_name == LLM_MODEL_NAME):
        # RQ already owns the bounded retries. A permanent failure waits for
        # input/config changes or an explicit admin rebuild.
        return row, False

    row.requested_hash = digest
    row.input_snapshot = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    row.prompt_version = PLAYER_SUMMARY_PROMPT_VERSION
    row.model_name = LLM_MODEL_NAME
    row.error_message = None
    if not llm_configured():
        row.status = 'blocked_configuration'
        row.error_message = 'LLM_API_KEY 未配置'
        row.save()
        return row, False
    queue = _queue()
    if queue is None:
        row.status = 'blocked_configuration'
        row.error_message = 'REDIS_URL 未配置'
        row.save()
        return row, False

    job_id = _player_summary_job_id(row.id, digest)
    existing = queue.fetch_job(job_id)
    if existing and existing.get_status(refresh=True) in (
            'queued', 'started', 'deferred', 'scheduled'):
        row.status = 'queued'
        row.save()
        return row, False
    if existing:
        try:
            existing.delete()
        except Exception:
            pass
    from rq import Retry
    queue.enqueue(
        run_player_summary,
        cup_name,
        player_id,
        digest,
        job_id=job_id,
        retry=Retry(max=3, interval=[60, 600, 3600]),
        job_timeout=120,
        result_ttl=86400,
        failure_ttl=7 * 86400,
    )
    row.status = 'queued'
    row.save()
    return row, True


def run_player_summary(cup_name, player_id, target_hash):
    row = _row(cup_name, player_id)
    snapshot = build_summary_input(cup_name, player_id)
    if not snapshot:
        row.status = 'failed'
        row.error_message = '选手在该赛季已无有效数据'
        row.save()
        return {'status': 'failed', 'reason': 'no_data'}
    current_hash = snapshot_hash(snapshot)
    if current_hash != target_hash:
        _, queued = schedule_player_summary(cup_name, player_id, force=True, snapshot=snapshot)
        return {'status': 'superseded', 'queued': queued}

    row.status = 'generating'
    row.attempt_count = int(row.attempt_count or 0) + 1
    row.error_message = None
    row.save()
    try:
        result = generate_summary(snapshot)
        usage = result.pop('usage', {})
        # A newer crawl may have requested another hash while this API call ran.
        row = _row(cup_name, player_id)
        if row.requested_hash != target_hash:
            return {'status': 'superseded'}
        with PlayerSeasonSummary._meta.database.atomic():
            row.headline = result['headline']
            row.overview = result['overview']
            row.strength = result['strength']
            row.weakness = result['weakness']
            row.style = result['style']
            row.sample_info = json.dumps(snapshot.get('样本') or {}, ensure_ascii=False)
            row.input_snapshot = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
            row.source_hash = target_hash
            row.requested_hash = target_hash
            row.status = 'completed'
            row.prompt_version = PLAYER_SUMMARY_PROMPT_VERSION
            row.model_name = LLM_MODEL_NAME
            row.prompt_tokens = usage.get('prompt_tokens')
            row.completion_tokens = usage.get('completion_tokens')
            row.total_tokens = usage.get('total_tokens')
            row.error_message = None
            row.generated_at = datetime.now()
            row.save()
        return {'status': 'completed', 'summary_id': row.id}
    except Exception as exc:
        row = _row(cup_name, player_id)
        if row.requested_hash == target_hash:
            row.status = 'failed'
            row.error_message = _safe_error(exc)
            row.save()
        logger.error(f'选手赛季点评生成失败 cup={cup_name} player={player_id}: {_safe_error(exc)}')
        raise


def reconcile_player_summaries(cup_name=None, force=False):
    """Backfill all missing/changed season-player summaries."""
    if not llm_configured():
        return {'eligible': 0, 'scheduled': 0, 'skipped': 0,
                'blocked_configuration': True}
    if not REDIS_URL:
        return {'eligible': 0, 'scheduled': 0, 'skipped': 0,
                'blocked_configuration': True}
    seasons = Season.select()
    if cup_name:
        seasons = seasons.where(Season.cup_name == cup_name)
    eligible = scheduled = skipped = 0
    for season in seasons:
        cup = season.cup_name
        peers = []
        player_ids = [
            row.player_id for row in
            MatchPlayer.select(MatchPlayer.player_id)
            .where(MatchPlayer.cup_name == cup).distinct()
        ]
        for player_id in player_ids:
            stats = MatchPlayer.get_match_exploit(cup, player_id, None)
            if stats:
                peers.append((player_id, stats))
        for player_id, _ in peers:
            eligible += 1
            snapshot = build_summary_input(cup, player_id, peers=peers)
            _, did_queue = schedule_player_summary(
                cup, player_id, force=force, snapshot=snapshot)
            if did_queue:
                scheduled += 1
            else:
                skipped += 1
    return {'eligible': eligible, 'scheduled': scheduled, 'skipped': skipped}
