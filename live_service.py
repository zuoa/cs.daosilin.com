"""Live-room URL normalization, profile lookup, and live-status helpers."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
import threading
import time
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

import requests

from ajlog import logger


class LiveRoomError(ValueError):
    """Raised when a live-room address cannot be parsed or resolved."""


@dataclass(frozen=True)
class LivePlatform:
    code: str
    name: str
    domain: str
    url_template: str


LIVE_PLATFORMS = {
    platform.code: platform for platform in (
        LivePlatform('DOUYU', '斗鱼', 'douyu.com', 'https://www.douyu.com/{room_id}'),
        LivePlatform('HUYA', '虎牙', 'huya.com', 'https://www.huya.com/{room_id}'),
        LivePlatform('BILIBILI', '哔哩哔哩', 'live.bilibili.com', 'https://live.bilibili.com/{room_id}'),
        LivePlatform('DOUYIN', '抖音', 'live.douyin.com', 'https://live.douyin.com/{room_id}'),
        LivePlatform('KUAISHOU', '快手', 'live.kuaishou.com', 'https://live.kuaishou.com/u/{room_id}'),
        LivePlatform('CC', '网易 CC', 'cc.163.com', 'https://cc.163.com/{room_id}'),
        LivePlatform('YY', 'YY', 'yy.com', 'https://www.yy.com/{room_id}'),
        LivePlatform('TWITCH', 'Twitch', 'twitch.tv', 'https://www.twitch.tv/{room_id}'),
    )
}

LIVE_STATUS_CACHE_SECONDS = 60
LIVE_STATUS_FAILURE_CACHE_SECONDS = 20
LIVE_STATUS_TIMEOUT_SECONDS = 3

_live_status_cache: dict[str, tuple[float, dict]] = {}
_live_status_cache_lock = threading.RLock()

_STATUS_ENDPOINTS = {
    'DOUYU': 'https://open.douyucdn.cn/api/RoomApi/room/{room_id}',
    'HUYA': 'https://mp.huya.com/cache.php?m=Live&do=profileRoom&roomid={room_id}',
    'BILIBILI': 'https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}',
}

_STATUS_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (compatible; cs.daosilin.com/1.0)',
}


def _platform_for_hostname(hostname: str):
    hostname = (hostname or '').lower()
    return next((
        platform for platform in LIVE_PLATFORMS.values()
        if hostname == platform.domain or hostname.endswith(f'.{platform.domain}')
    ), None)


def _room_id_from_url(parsed) -> str:
    query = parse_qs(parsed.query)
    for key in ('room_id', 'roomid', 'room', 'id'):
        values = query.get(key) or []
        if values and values[0].strip():
            return values[0].strip()
    parts = [unquote(part).strip() for part in parsed.path.split('/') if part.strip()]
    return parts[-1] if parts else ''


def normalize_live_room(platform_code: str, room_or_url: str) -> dict:
    """Return a canonical platform, room ID and URL for a room input."""
    requested_platform = (platform_code or '').strip().upper()
    value = (room_or_url or '').strip()
    if not value:
        return {'platform': requested_platform, 'room_id': '', 'live_url': ''}

    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc:
        if parsed.scheme not in ('http', 'https') or not parsed.hostname:
            raise LiveRoomError('直播间地址必须是有效的 http(s) URL')
        detected = _platform_for_hostname(parsed.hostname)
        if not detected:
            raise LiveRoomError('暂不支持该直播平台地址')
        platform = detected
        room_id = _room_id_from_url(parsed)
    else:
        platform = LIVE_PLATFORMS.get(requested_platform)
        if not platform:
            raise LiveRoomError('请先选择直播平台')
        room_id = value.strip('/')

    if not room_id or any(char.isspace() for char in room_id):
        raise LiveRoomError('无法从输入中识别直播间号')
    return {
        'platform': platform.code,
        'platform_name': platform.name,
        'room_id': room_id,
        'live_url': platform.url_template.format(room_id=room_id),
    }


def fetch_live_avatar(platform_code: str, room_id: str, timeout: int = 8) -> str:
    """Fetch a broadcaster avatar. Douyu is the first supported provider."""
    platform_code = (platform_code or '').strip().upper()
    room_id = (room_id or '').strip()
    if platform_code != 'DOUYU':
        raise LiveRoomError('当前仅支持获取斗鱼直播间头像')
    if not room_id:
        raise LiveRoomError('请填写斗鱼直播间号')

    try:
        response = requests.get(
            f'https://open.douyucdn.cn/api/RoomApi/room/{room_id}',
            headers={'Accept': 'application/json', 'User-Agent': 'cs.daosilin.com/1.0'},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise LiveRoomError('获取斗鱼直播间信息失败，请稍后重试') from exc

    data = payload.get('data') if isinstance(payload, dict) else None
    avatar = (data or {}).get('avatar')
    if payload.get('error') != 0 or not avatar:
        raise LiveRoomError('未找到该斗鱼直播间或主播头像')
    parsed_avatar = urlsplit(avatar)
    if parsed_avatar.scheme not in ('http', 'https') or not parsed_avatar.hostname:
        raise LiveRoomError('斗鱼返回了无效的头像地址')
    return avatar


def resolve_live_room(platform_code: str, room_or_url: str, include_avatar: bool = False) -> dict:
    result = normalize_live_room(platform_code, room_or_url)
    result['avatar_supported'] = result.get('platform') == 'DOUYU'
    if include_avatar:
        result['avatar'] = fetch_live_avatar(result.get('platform'), result.get('room_id'))
    return result


def _cached_live_status(cache_key: str) -> Optional[dict]:
    now = time.monotonic()
    with _live_status_cache_lock:
        item = _live_status_cache.get(cache_key)
        if not item:
            return None
        expires_at, result = item
        if expires_at <= now:
            _live_status_cache.pop(cache_key, None)
            return None
        return result.copy()


def _store_live_status(cache_key: str, result: dict, ttl: int) -> None:
    with _live_status_cache_lock:
        _live_status_cache[cache_key] = (time.monotonic() + ttl, result.copy())


def clear_live_status_cache() -> None:
    """Clear the process-local status cache, primarily for tests."""
    with _live_status_cache_lock:
        _live_status_cache.clear()


def _parse_live_status(platform_code: str, payload: object) -> str:
    if not isinstance(payload, dict):
        return 'unknown'

    if platform_code == 'DOUYU':
        data = payload.get('data')
        if payload.get('error') != 0 or not isinstance(data, dict):
            return 'unknown'
        status = str(data.get('room_status') or '').strip()
        return 'live' if status == '1' else 'offline' if status == '0' else 'unknown'

    if platform_code == 'HUYA':
        data = payload.get('data')
        if payload.get('status') != 200 or not isinstance(data, dict):
            return 'unknown'
        status = str(data.get('liveStatus') or '').strip().upper()
        return 'live' if status == 'ON' else 'offline' if status in ('OFF', 'REPLAY') else 'unknown'

    if platform_code == 'BILIBILI':
        data = payload.get('data')
        if payload.get('code') != 0 or not isinstance(data, dict):
            return 'unknown'
        try:
            status = int(data.get('live_status'))
        except (TypeError, ValueError):
            return 'unknown'
        return 'live' if status == 1 else 'offline' if status in (0, 2) else 'unknown'

    return 'unknown'


def get_live_status(platform_code: str, room_id: str,
                    timeout: float = LIVE_STATUS_TIMEOUT_SECONDS) -> dict:
    """Return a best-effort live state without allowing upstream errors to escape."""
    platform_code = (platform_code or '').strip().upper()
    room_id = (room_id or '').strip()
    supported = platform_code in _STATUS_ENDPOINTS
    result = {
        'platform': platform_code,
        'status': 'unknown',
        'supported': supported,
    }
    if not supported or not room_id:
        return result

    cache_key = f'{platform_code}:{room_id}'
    cached = _cached_live_status(cache_key)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            _STATUS_ENDPOINTS[platform_code].format(room_id=room_id),
            headers=_STATUS_HEADERS,
            timeout=timeout,
        )
        response.raise_for_status()
        result['status'] = _parse_live_status(platform_code, response.json())
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.warning(f'查询直播状态失败 platform={platform_code} room_id={room_id}: {exc}')

    ttl = LIVE_STATUS_CACHE_SECONDS if result['status'] != 'unknown' else LIVE_STATUS_FAILURE_CACHE_SECONDS
    _store_live_status(cache_key, result, ttl)
    return result.copy()


def get_live_statuses(live_rooms: dict[str, str]) -> dict[str, dict]:
    """Resolve and check several configured rooms concurrently."""
    resolved = {}
    for player_id, live_url in (live_rooms or {}).items():
        try:
            room = normalize_live_room('', live_url)
        except LiveRoomError:
            resolved[str(player_id)] = None
            continue
        if room.get('room_id'):
            resolved[str(player_id)] = room

    if not resolved:
        return {}

    statuses = {}
    with ThreadPoolExecutor(max_workers=min(6, len(resolved))) as executor:
        futures = {
            executor.submit(get_live_status, room['platform'], room['room_id']): player_id
            for player_id, room in resolved.items() if room
        }
        for future in as_completed(futures):
            player_id = futures[future]
            try:
                statuses[player_id] = future.result()
            except Exception as exc:  # Guard the batch if a future provider is added incorrectly.
                logger.warning(f'批量查询直播状态失败 player_id={player_id}: {exc}')
                statuses[player_id] = {
                    'platform': resolved[player_id]['platform'],
                    'status': 'unknown',
                    'supported': False,
                }
    return statuses
