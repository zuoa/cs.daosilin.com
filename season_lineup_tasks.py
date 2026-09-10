"""RQ producer and worker job for multi-ballot season lineups."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from ajlog import logger
from cache_service import invalidate_season
from config import (LLM_API_KEY, LLM_MODEL_NAME, REDIS_URL,
                    SEASON_LINEUP_BALLOTS, SEASON_LINEUP_PROMPT_VERSION)
from database import Season, SeasonLineupRun
from season_lineup_service import (PERSPECTIVES, LineupValidationError,
                                   aggregate_ballots, build_selection_snapshot,
                                   generate_ballot,
                                   llm_configured, snapshot_hash)


def _safe_error(exc) -> str:
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
    return Queue('season-lineup', connection=Redis.from_url(REDIS_URL),
                 serializer=JSONSerializer, default_timeout=1800)


def _latest_same(cup: str, digest: str):
    return (SeasonLineupRun.select().where(
        SeasonLineupRun.cup_name == cup,
        SeasonLineupRun.requested_hash == digest,
        SeasonLineupRun.prompt_version == SEASON_LINEUP_PROMPT_VERSION,
        SeasonLineupRun.model_name == LLM_MODEL_NAME,
    ).order_by(SeasonLineupRun.id.desc()).first())


def schedule_season_lineup(cup: str, *, final: bool = False):
    """Freeze current data and idempotently schedule a 21-ballot selection."""
    season = Season.get_by_cup(cup)
    if not season:
        raise LineupValidationError('赛季不存在')
    final = bool(final or season.get('status') == 'archived')
    try:
        snapshot = build_selection_snapshot(cup)
        digest = snapshot_hash(snapshot)
    except LineupValidationError as exc:
        row = SeasonLineupRun.create(
            cup_name=cup, status='insufficient_data', is_final=False,
            ballot_target=SEASON_LINEUP_BALLOTS,
            prompt_version=SEASON_LINEUP_PROMPT_VERSION,
            model_name=LLM_MODEL_NAME, error_message=str(exc),
        )
        return row, False

    existing = _latest_same(cup, digest)
    if existing and existing.status == 'completed':
        if final and not existing.is_final:
            existing.is_final = True
            existing.save()
            invalidate_season(cup, external=False)
        return existing, False
    if existing and existing.status in ('pending', 'queued', 'generating'):
        if final and not existing.is_final:
            existing.is_final = True
            existing.save()
        return existing, False

    row = SeasonLineupRun.create(
        cup_name=cup,
        status='pending',
        is_final=final,
        ballot_target=SEASON_LINEUP_BALLOTS,
        requested_hash=digest,
        prompt_version=SEASON_LINEUP_PROMPT_VERSION,
        model_name=LLM_MODEL_NAME,
        input_snapshot=json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
    )
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

    from rq import Retry
    job_id = f'season-lineup-{row.id}-{digest[:16]}'
    queue.enqueue(
        run_season_lineup, row.id, digest,
        job_id=job_id,
        retry=Retry(max=3, interval=[60, 600, 3600]),
        job_timeout=1800,
        result_ttl=86400,
        failure_ttl=7 * 86400,
    )
    row.status = 'queued'
    row.save()
    return row, True


def _one_ballot(snapshot, perspective: str, ballot_index: int):
    last_error = None
    for _attempt in range(2):
        try:
            return generate_ballot(snapshot, perspective, ballot_index)
        except Exception as exc:
            last_error = exc
    raise last_error


def _run_season_lineup(run_id: int, target_hash: str):
    row = SeasonLineupRun.get(SeasonLineupRun.id == run_id)
    snapshot = json.loads(row.input_snapshot or '{}')
    if snapshot_hash(snapshot) != target_hash or row.requested_hash != target_hash:
        row.status = 'superseded'
        row.save()
        return {'status': 'superseded'}
    row.status = 'generating'
    row.error_message = None
    row.save()

    assignments = []
    per_perspective = max(1, SEASON_LINEUP_BALLOTS // len(PERSPECTIVES))
    ballot_index = 0
    for perspective in PERSPECTIVES:
        for _ in range(per_perspective):
            ballot_index += 1
            assignments.append((perspective, ballot_index))
    while len(assignments) < SEASON_LINEUP_BALLOTS:
        perspective = PERSPECTIVES[len(assignments) % len(PERSPECTIVES)]
        ballot_index += 1
        assignments.append((perspective, ballot_index))

    ballots = []
    usages = []
    errors = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_one_ballot, snapshot, perspective, index): (perspective, index)
            for perspective, index in assignments
        }
        for future in as_completed(futures):
            perspective, index = futures[future]
            try:
                ballot, usage = future.result()
                ballots.append(ballot)
                usages.append(usage)
            except Exception as exc:
                errors.append(f'{perspective}#{index}: {_safe_error(exc)}')

    ballots.sort(key=lambda item: item['ballot_index'])
    counts = Counter(ballot['perspective'] for ballot in ballots)
    quorum = max(1, math.ceil(per_perspective * 4 / 7))
    minimum_valid = max(1, math.ceil(SEASON_LINEUP_BALLOTS * 5 / 7))
    if len(ballots) < minimum_valid or any(
            counts[perspective] < quorum for perspective in PERSPECTIVES):
        row.status = 'failed'
        row.valid_ballots = len(ballots)
        row.ballots_json = json.dumps(ballots, ensure_ascii=False, separators=(',', ':'))
        row.error_message = (
            f'有效选票不足：{len(ballots)}/{SEASON_LINEUP_BALLOTS}，'
            f'分层 {dict(counts)}。' + ('; '.join(errors[:3]) if errors else '')
        )[:2000]
        row.save()
        return {'status': 'failed', 'valid_ballots': len(ballots)}

    current = build_selection_snapshot(row.cup_name)
    if snapshot_hash(current) != target_hash:
        row.status = 'superseded'
        row.valid_ballots = len(ballots)
        row.ballots_json = json.dumps(ballots, ensure_ascii=False, separators=(',', ':'))
        row.error_message = '评选期间赛季数据已更新，本轮未发布'
        row.save()
        if (Season.get_by_cup(row.cup_name) or {}).get('status') == 'archived':
            schedule_season_lineup(row.cup_name, final=True)
        return {'status': 'superseded'}

    result = aggregate_ballots(ballots, snapshot)
    token = lambda key: sum(int(usage.get(key) or 0) for usage in usages)
    row.status = 'completed'
    row.valid_ballots = len(ballots)
    row.ballots_json = json.dumps(ballots, ensure_ascii=False, separators=(',', ':'))
    row.result_json = json.dumps(result, ensure_ascii=False, separators=(',', ':'))
    row.source_hash = target_hash
    row.prompt_tokens = token('prompt_tokens')
    row.completion_tokens = token('completion_tokens')
    row.total_tokens = token('total_tokens')
    row.error_message = None
    row.generated_at = datetime.now()
    row.save()
    invalidate_season(row.cup_name, external=False)
    return {'status': 'completed', 'run_id': row.id, 'valid_ballots': len(ballots)}


def run_season_lineup(run_id: int, target_hash: str):
    try:
        return _run_season_lineup(run_id, target_hash)
    except Exception as exc:
        row = SeasonLineupRun.get_or_none(SeasonLineupRun.id == run_id)
        if row and row.status != 'completed':
            row.status = 'failed'
            row.error_message = _safe_error(exc)
            row.save()
        logger.error(f'赛季阵容评选失败 run={run_id}: {_safe_error(exc)}')
        raise


__all__ = ['schedule_season_lineup', 'run_season_lineup']
