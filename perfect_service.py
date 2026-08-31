"""Perfect World Arena player rank lookup.

The public search endpoint returns a player's current PVP score.  The rank
label is calculated locally because the endpoint does not expose the label
used by the client.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Dict, Optional

import requests

from ajlog import logger


PERFECT_SEARCH_URL = 'https://appengine.wmpvp.com/steamcn/app/search/user'
PERFECT_DETAIL_URL = 'https://api.wmpvp.com/api/csgo/home/pvp/detailStats'
STEAM_ID64_BASE = 76561197960265728
PERFECT_RANK_CACHE_SECONDS = 300
PERFECT_RANK_FAILURE_CACHE_SECONDS = 60

_REQUEST_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json;charset=UTF-8',
    'Origin': 'https://news.wmpvp.com',
    'Referer': 'https://client.wmpvp.com',
    'User-Agent': 'Mozilla/5.0',
    'x-requested-with': 'XMLHttpRequest',
}

_DETAIL_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Content-Type': 'application/json;charset=UTF-8',
    'Referer': 'https://news.wmpvp.com/',
    'User-Agent': 'Mozilla/5.0 (Linux; Android 15) EsportsApp',
    'appversion': '3.6.6.192',
    'device': 'rank-enrichment',
    'platform': 'h5_android',
    'gameType': '2',
    'gameTypeStr': '2',
}

_cache: Dict[str, tuple[float, Optional[Dict[str, Any]]]] = {}
_cache_lock = threading.RLock()


def to_steam_id64(value: object) -> Optional[str]:
    """Normalize common Steam ID formats to a SteamID64 string."""
    raw = str(value or '').strip()
    if re.fullmatch(r'\d{17}', raw):
        return raw

    steam2 = re.fullmatch(r'STEAM_\d:([01]):(\d+)', raw, re.IGNORECASE)
    if steam2:
        account_id = int(steam2.group(2)) * 2 + int(steam2.group(1))
        return str(STEAM_ID64_BASE + account_id)

    steam3 = re.fullmatch(r'\[U:1:(\d+)\]', raw, re.IGNORECASE)
    if steam3:
        return str(STEAM_ID64_BASE + int(steam3.group(1)))

    if re.fullmatch(r'\d{1,10}', raw):
        return str(STEAM_ID64_BASE + int(raw))
    return None


def resolve_steam_id64(*candidates: object) -> Optional[str]:
    """Return the first candidate that can be normalized to SteamID64."""
    for candidate in candidates:
        steam_id = to_steam_id64(candidate)
        if steam_id:
            return steam_id
    return None


def perfect_level(score: object) -> str:
    """Map the integer PVP score to the S21+ Perfect World rank system."""
    try:
        value = int(float(score or 0))
    except (TypeError, ValueError):
        value = 0

    if value <= 0:
        return '未定级'

    thresholds = (
        (1000, 'D'),
        (1150, 'C'),
        (1300, 'C+'),
        (1450, '精英 C'),
        (1600, 'B'),
        (1750, 'B+'),
        (1900, '精英 B'),
        (2050, 'A'),
        (2200, 'A+'),
        (2400, '精英 A'),
    )
    for maximum, level in thresholds:
        if value <= maximum:
            return level
    return 'S'


def _cached(steam_id: str) -> tuple[bool, Optional[Dict[str, Any]]]:
    now = time.monotonic()
    with _cache_lock:
        item = _cache.get(steam_id)
        if not item:
            return False, None
        expires_at, value = item
        if expires_at <= now:
            _cache.pop(steam_id, None)
            return False, None
        return True, value.copy() if value is not None else None


def _store(steam_id: str, value: Optional[Dict[str, Any]], ttl: int) -> None:
    stored = value.copy() if value is not None else None
    with _cache_lock:
        _cache[steam_id] = (time.monotonic() + ttl, stored)


def clear_perfect_rank_cache() -> None:
    """Clear the process-local cache (primarily useful for tests)."""
    with _cache_lock:
        _cache.clear()


def _optional_nonnegative_int(value: object) -> Optional[int]:
    if value is None or value == '':
        return None
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return None


def _get_perfect_s_detail(
    steam_id: str,
    credential: Optional[Dict[str, str]],
    timeout: float,
) -> Optional[Dict[str, Optional[int]]]:
    """Return the authenticated current S score and stars when available."""
    if not credential:
        return None
    access_token = str(credential.get('access_token') or '').strip()
    my_steam_id = to_steam_id64(credential.get('steam_id'))
    if not access_token or not my_steam_id:
        return None

    try:
        response = requests.post(
            PERFECT_DETAIL_URL,
            headers={
                **_DETAIL_HEADERS,
                # Current clients use accessToken; token keeps older API
                # deployments compatible without changing the request body.
                'accessToken': access_token,
                'token': access_token,
            },
            json={
                'accessToken': '',
                'mySteamId': int(my_steam_id),
                'toSteamId': int(steam_id),
                'csgoSeasonId': 'recent',
            },
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get('data') if isinstance(payload, dict) else None
        if payload.get('statusCode') != 0 or not isinstance(data, dict):
            return None
        # The live API currently leaves top-level pvpScore/stars at placeholder
        # values for S players. scoreList is the per-match history and its
        # newest row contains both the effective score and star count.
        score_items = [
            item for item in (data.get('scoreList') or [])
            if isinstance(item, dict)
        ]
        if any(isinstance(item.get('time'), (int, float)) for item in score_items):
            score_items.sort(
                key=lambda item: item.get('time')
                if isinstance(item.get('time'), (int, float)) else -1,
                reverse=True,
            )
        if score_items:
            latest = score_items[0]
            return {
                'score': _optional_nonnegative_int(latest.get('score')),
                'stars': _optional_nonnegative_int(latest.get('stars')),
            }
        return {
            'score': _optional_nonnegative_int(data.get('pvpScore')),
            'stars': _optional_nonnegative_int(data.get('stars')),
        }
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        # Star enrichment is optional: a stale credential must not discard the
        # rank already obtained from the public search endpoint.
        logger.warning(f'查询完美 S 段详情失败 steam_id={steam_id}: {exc}')
        return None


def get_perfect_rank(
    steam_id: object,
    timeout: float = 4.0,
    credential: Optional[Dict[str, str]] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch a player's current Perfect World score and calculated rank.

    Network and upstream-data failures intentionally return ``None`` so an
    unavailable third-party service never prevents the player page loading.
    """
    normalized = to_steam_id64(steam_id)
    if not normalized:
        return None

    cache_key = f'{normalized}:auth' if credential else f'{normalized}:public'
    hit, cached_value = _cached(cache_key)
    if hit:
        return cached_value

    try:
        response = requests.post(
            PERFECT_SEARCH_URL,
            headers=_REQUEST_HEADERS,
            json={'keyword': normalized, 'page': 1},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError('unexpected Perfect World response type')
        if payload.get('code') != 1 or not isinstance(payload.get('result'), list):
            raise ValueError(f"unexpected Perfect World response code: {payload.get('code')}")

        player = next((
            item for item in payload['result']
            if str(item.get('steamId') or '').strip() == normalized
        ), None)
        if player is None:
            _store(cache_key, None, PERFECT_RANK_FAILURE_CACHE_SECONDS)
            return None

        try:
            score = int(float(player.get('pvpScore') or 0))
        except (TypeError, ValueError):
            score = 0
        level = perfect_level(score)
        s_detail = _get_perfect_s_detail(normalized, credential, timeout) if level == 'S' else None
        stars = s_detail.get('stars') if s_detail else None
        detail_score = s_detail.get('score') if s_detail else None
        if detail_score and detail_score >= score:
            score = detail_score
        result = {
            'steam_id': normalized,
            'nickname': player.get('pvpNickName') or '',
            'score': score,
            'level': level,
            'stars': stars,
            'is_ranked': score > 0,
            'is_elite': level.startswith('精英'),
            'score_capped': level == 'S' and score == 2401,
            'source': 'perfect_world',
        }
        _store(cache_key, result, PERFECT_RANK_CACHE_SECONDS)
        return result.copy()
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(f'查询完美段位失败 steam_id={normalized}: {exc}')
        _store(cache_key, None, PERFECT_RANK_FAILURE_CACHE_SECONDS)
        return None
