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


def get_perfect_rank(steam_id: object, timeout: float = 4.0) -> Optional[Dict[str, Any]]:
    """Fetch a player's current Perfect World score and calculated rank.

    Network and upstream-data failures intentionally return ``None`` so an
    unavailable third-party service never prevents the player page loading.
    """
    normalized = to_steam_id64(steam_id)
    if not normalized:
        return None

    hit, cached_value = _cached(normalized)
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
            _store(normalized, None, PERFECT_RANK_FAILURE_CACHE_SECONDS)
            return None

        try:
            score = int(float(player.get('pvpScore') or 0))
        except (TypeError, ValueError):
            score = 0
        level = perfect_level(score)
        result = {
            'steam_id': normalized,
            'nickname': player.get('pvpNickName') or '',
            'score': score,
            'level': level,
            'is_ranked': score > 0,
            'is_elite': level.startswith('精英'),
            'score_capped': level == 'S' and score == 2401,
            'source': 'perfect_world',
        }
        _store(normalized, result, PERFECT_RANK_CACHE_SECONDS)
        return result.copy()
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(f'查询完美段位失败 steam_id={normalized}: {exc}')
        _store(normalized, None, PERFECT_RANK_FAILURE_CACHE_SECONDS)
        return None
