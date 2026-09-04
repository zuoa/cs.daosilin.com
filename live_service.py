"""Live-room URL normalization, profile lookup, and live-status helpers."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from html import unescape as html_unescape
import json
import re
import threading
import time
from typing import Optional
from urllib.parse import parse_qs, unquote, urlsplit

import requests
from urllib3.util import Timeout as Urllib3Timeout

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
LIVE_STATUS_BATCH_BUDGET_SECONDS = 20
HUYA_STATUS_CONNECT_TIMEOUT_SECONDS = 3
HUYA_STATUS_READ_TIMEOUT_SECONDS = 8
HUYA_STATUS_TIMEOUT_RETRIES = 1

_live_status_cache: dict[str, tuple[float, dict]] = {}
_live_status_cache_lock = threading.RLock()

_STATUS_ENDPOINTS = {
    # The legacy RoomApi marks video loops as live. betard exposes videoLoop,
    # allowing a real broadcast to be distinguished from round-robin video.
    'DOUYU': 'https://www.douyu.com/betard/{room_id}',
    'HUYA': (
        'https://mp.huya.com/cache.php?m=Live&do=profileRoom'
        '&roomid={room_id}&showSecret=1'
    ),
    'BILIBILI': 'https://api.live.bilibili.com/room/v1/Room/get_info?room_id={room_id}',
}

_STATUS_HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'User-Agent': 'Mozilla/5.0 (compatible; cs.daosilin.com/1.0)',
}

_HUYA_PROFILE_ENDPOINT = 'https://mp.huya.com/cache.php'
_HUYA_ROOM_ENDPOINT = 'https://www.huya.com/{room_id}'
_HUYA_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/125.0.0.0 Safari/537.36'
)
_HUYA_ROOM_DATA_PATTERN = re.compile(
    r'\bvar\s+TT_ROOM_DATA\s*=\s*(\{.*?\})\s*;', re.DOTALL,
)


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
        room = payload.get('room')
        if isinstance(room, dict):
            video_loop = room.get('videoLoop')
            room_biz = room.get('room_biz_all')
            if video_loop is None and isinstance(room_biz, dict):
                video_loop = room_biz.get('videoLoop')
            if str(video_loop or '').strip().lower() in ('1', 'true'):
                return 'offline'
            status = str(room.get('show_status') or '').strip()
            return 'live' if status == '1' else 'offline' if status in ('0', '2') else 'unknown'

        # Retain compatibility with the older RoomApi response shape.
        data = payload.get('data')
        if payload.get('error') != 0 or not isinstance(data, dict):
            return 'unknown'
        status = str(data.get('room_status') or '').strip()
        return 'live' if status == '1' else 'offline' if status == '0' else 'unknown'

    if platform_code == 'HUYA':
        data = payload.get('data')
        if payload.get('status') != 200 or not isinstance(data, dict):
            return 'unknown'
        # realLiveStatus excludes replay/round-robin video when Huya still
        # exposes the room as playable through liveStatus.
        status = str(data.get('realLiveStatus') or data.get('liveStatus') or '').strip().upper()
        return 'live' if status == 'ON' else 'offline' if status in ('OFF', 'REPLAY') else 'unknown'

    if platform_code == 'BILIBILI':
        data = payload.get('data')
        if payload.get('code') != 0 or not isinstance(data, dict):
            return 'unknown'
        round_status = data.get('round_status', data.get('roundStatus'))
        if str(round_status or '').strip() == '1':
            return 'offline'
        try:
            status = int(data.get('live_status'))
        except (TypeError, ValueError):
            return 'unknown'
        # Bilibili uses 2 for round-robin playback, which is not a live show.
        return 'live' if status == 1 else 'offline' if status in (0, 2) else 'unknown'

    return 'unknown'


def _parse_huya_page_status(page: str) -> str:
    """Extract Huya's room state from the data embedded in its web page."""
    match = _HUYA_ROOM_DATA_PATTERN.search(html_unescape(page or ''))
    if not match:
        return 'unknown'
    try:
        room = json.loads(match.group(1))
    except (TypeError, ValueError):
        return 'unknown'
    if not isinstance(room, dict):
        return 'unknown'

    is_replay = str(room.get('isReplay') or '').strip().lower()
    if is_replay in ('1', 'true'):
        return 'offline'
    state = str(room.get('state') or '').strip().upper()
    if state == 'ON':
        return 'live'
    if state in ('OFF', 'REPLAY'):
        return 'offline'
    return 'unknown'


def _request_deadline(timeout: Optional[float] = None,
                      deadline: Optional[float] = None) -> float:
    """Return the earlier of the per-room and enclosing request deadlines."""
    budget = LIVE_STATUS_TIMEOUT_SECONDS if timeout is None else max(0.0, float(timeout))
    room_deadline = time.monotonic() + budget
    return min(room_deadline, deadline) if deadline is not None else room_deadline


def _remaining_timeout(deadline: float, connect: Optional[float] = None,
                       read: Optional[float] = None):
    """Build one request timeout from the remaining shared wall-clock budget."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise requests.Timeout('直播状态查询已超过总时限')
    return Urllib3Timeout(
        total=remaining,
        connect=min(connect, remaining) if connect is not None else remaining,
        read=min(read, remaining) if read is not None else remaining,
    )


def _get_huya_live_status(room_id: str, timeout: Optional[float] = None,
                          deadline: Optional[float] = None) -> str:
    """Query Huya's mobile endpoint, falling back to its public room page."""
    referer = _HUYA_ROOM_ENDPOINT.format(room_id=room_id)
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Referer': referer,
        'User-Agent': _HUYA_USER_AGENT,
        'xweb_xhr': '1',
    }
    deadline = _request_deadline(timeout, deadline)
    profile_error = None
    for attempt in range(HUYA_STATUS_TIMEOUT_RETRIES + 1):
        try:
            request_timeout = _remaining_timeout(
                deadline,
                connect=HUYA_STATUS_CONNECT_TIMEOUT_SECONDS,
                read=HUYA_STATUS_READ_TIMEOUT_SECONDS,
            )
            response = requests.get(
                _HUYA_PROFILE_ENDPOINT,
                params={
                    'm': 'Live',
                    'do': 'profileRoom',
                    'roomid': room_id,
                    'showSecret': '1',
                },
                headers=headers,
                timeout=request_timeout,
            )
            response.raise_for_status()
            status = _parse_live_status('HUYA', response.json())
            if status != 'unknown':
                return status
            profile_error = LiveRoomError('虎牙小程序接口返回了未知状态')
            break
        except requests.Timeout as exc:
            profile_error = exc
            if attempt < HUYA_STATUS_TIMEOUT_RETRIES:
                continue
            break
        except (requests.RequestException, ValueError, TypeError) as exc:
            profile_error = exc
            break

    try:
        request_timeout = _remaining_timeout(
            deadline,
            connect=HUYA_STATUS_CONNECT_TIMEOUT_SECONDS,
            read=HUYA_STATUS_READ_TIMEOUT_SECONDS,
        )
        response = requests.get(
            referer,
            headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9',
                'Referer': 'https://www.huya.com/',
                'User-Agent': _HUYA_USER_AGENT,
            },
            timeout=request_timeout,
        )
        response.raise_for_status()
        status = _parse_huya_page_status(response.text)
        if status != 'unknown':
            return status
        raise LiveRoomError('虎牙直播间页面未包含可识别的状态')
    except (requests.RequestException, ValueError, TypeError) as page_error:
        raise LiveRoomError(
            f'虎牙小程序接口失败 ({profile_error}); 网页回退失败 ({page_error})'
        ) from page_error


def get_live_status(platform_code: str, room_id: str,
                    timeout: Optional[float] = None,
                    deadline: Optional[float] = None) -> dict:
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
        if platform_code == 'HUYA':
            result['status'] = _get_huya_live_status(
                room_id,
                timeout=timeout,
                deadline=deadline,
            )
        else:
            request_deadline = _request_deadline(timeout, deadline)
            response = requests.get(
                _STATUS_ENDPOINTS[platform_code].format(room_id=room_id),
                headers=_STATUS_HEADERS,
                timeout=_remaining_timeout(request_deadline),
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
    deadline = time.monotonic() + LIVE_STATUS_BATCH_BUDGET_SECONDS
    with ThreadPoolExecutor(max_workers=min(6, len(resolved))) as executor:
        futures = {
            executor.submit(
                get_live_status,
                room['platform'],
                room['room_id'],
                deadline=deadline,
            ): player_id
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
