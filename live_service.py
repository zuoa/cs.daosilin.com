"""Live-room URL normalization, profile lookup, and live-status helpers."""
from concurrent.futures import (FIRST_COMPLETED, ThreadPoolExecutor,
                                TimeoutError as FuturesTimeoutError,
                                as_completed, wait)
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

LIVE_STATUS_CACHE_SECONDS = 60 * 60
LIVE_STATUS_FAILURE_CACHE_SECONDS = 60 * 60
LIVE_STATUS_LAST_GOOD_SECONDS = 24 * 60 * 60
LIVE_STATUS_TIMEOUT_SECONDS = 3
LIVE_STATUS_BATCH_BUDGET_SECONDS = 20
HUYA_STATUS_CONNECT_TIMEOUT_SECONDS = 3
HUYA_STATUS_READ_TIMEOUT_SECONDS = 8
HUYA_FALLBACK_HEDGE_SECONDS = 0.4

_live_status_cache: dict[str, tuple[float, dict]] = {}
_last_good_live_status: dict[str, dict] = {}
_live_status_key_locks: dict[str, threading.Lock] = {}
_shared_live_status_keys: set[str] = set()
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
_HUYA_MOBILE_ROOM_ENDPOINT = 'https://m.huya.com/{room_id}'
_HUYA_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/125.0.0.0 Safari/537.36'
)
_HUYA_MOBILE_USER_AGENT = (
    'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
    'Mobile/15E148 Safari/604.1'
)
_HUYA_ROOM_DATA_PATTERN = re.compile(
    r'\bvar\s+TT_ROOM_DATA\s*=\s*(\{.*?\})\s*;', re.DOTALL,
)
_HUYA_MOBILE_DATA_PATTERN = re.compile(
    r'\bwindow\.HNF_GLOBAL_INIT\s*=\s*(\{.*?\})\s*;?\s*</script>',
    re.DOTALL,
)


@dataclass(frozen=True)
class _HuyaStatusObservation:
    status: str
    source: str
    real_live_status: bool = False


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


def _shared_status_cache_key(cache_key: str) -> str:
    return f'live-status:{cache_key}'


def _shared_last_good_cache_key(cache_key: str) -> str:
    return f'live-status-last-good:{cache_key}'


def _shared_redis_key(cache_key: str) -> str:
    # Keep scheduled live-state JSON separate from Flask-Caching's pickled keys.
    return f'cs:scheduled-{cache_key}'


def _shared_cache_get(cache_key: str) -> Optional[dict]:
    try:
        from cache_service import _redis_client
        client = _redis_client()
        if client is None:
            return None
        value = client.get(_shared_redis_key(cache_key))
        value = json.loads(value) if value else None
    except Exception as exc:
        logger.warning(f'直播状态共享缓存读取失败 key={cache_key}: {exc}')
        return None
    return value.copy() if isinstance(value, dict) else None


def _shared_cache_set(cache_key: str, result: dict, ttl: int) -> None:
    try:
        from cache_service import _redis_client
        client = _redis_client()
        if client is None:
            return
        redis_key = _shared_redis_key(cache_key)
        client.set(redis_key, json.dumps(result, ensure_ascii=False), ex=ttl)
        with _live_status_cache_lock:
            _shared_live_status_keys.add(redis_key)
    except Exception as exc:
        logger.warning(f'直播状态共享缓存写入失败 key={cache_key}: {exc}')


def _cached_live_status(cache_key: str) -> Optional[dict]:
    now = time.monotonic()
    with _live_status_cache_lock:
        item = _live_status_cache.get(cache_key)
        if item:
            expires_at, result = item
            if expires_at > now:
                return result.copy()
            _live_status_cache.pop(cache_key, None)
    return _shared_cache_get(_shared_status_cache_key(cache_key))


def _store_live_status(cache_key: str, result: dict, ttl: int) -> None:
    with _live_status_cache_lock:
        _live_status_cache[cache_key] = (time.monotonic() + ttl, result.copy())
    _shared_cache_set(_shared_status_cache_key(cache_key), result, ttl)


def _last_good_status(cache_key: str) -> Optional[dict]:
    with _live_status_cache_lock:
        result = _last_good_live_status.get(cache_key)
        if result is not None:
            return result.copy()
    return _shared_cache_get(_shared_last_good_cache_key(cache_key))


def _store_last_good_status(cache_key: str, result: dict) -> None:
    with _live_status_cache_lock:
        _last_good_live_status[cache_key] = result.copy()
    _shared_cache_set(
        _shared_last_good_cache_key(cache_key),
        result,
        LIVE_STATUS_LAST_GOOD_SECONDS,
    )


def _live_status_key_lock(cache_key: str) -> threading.Lock:
    with _live_status_cache_lock:
        return _live_status_key_locks.setdefault(cache_key, threading.Lock())


def clear_live_status_cache() -> None:
    """Clear the process-local status cache, primarily for tests."""
    with _live_status_cache_lock:
        shared_keys = tuple(_shared_live_status_keys)
        _live_status_cache.clear()
        _last_good_live_status.clear()
        _live_status_key_locks.clear()
        _shared_live_status_keys.clear()
    if shared_keys:
        try:
            from cache_service import _redis_client
            client = _redis_client()
            if client is not None:
                client.delete(*shared_keys)
        except Exception:
            pass


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


def _parse_huya_mobile_page_status(page: str) -> str:
    """Extract Huya's room state from the mobile page's SSR bootstrap data."""
    match = _HUYA_MOBILE_DATA_PATTERN.search(html_unescape(page or ''))
    if not match:
        return 'unknown'
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return 'unknown'
    room = payload.get('roomInfo') if isinstance(payload, dict) else None
    if not isinstance(room, dict):
        return 'unknown'

    replay = room.get('tReplayInfo')
    if isinstance(replay, dict) and str(replay.get('lUid') or '').strip() not in ('', '0'):
        return 'offline'
    try:
        status = int(room.get('eLiveStatus'))
    except (TypeError, ValueError):
        return 'unknown'
    # Huya's mobile SSR enum uses 2 for a real live show, 1 for offline,
    # and 3 for replay. A replay must not light up the live indicator.
    return 'live' if status == 2 else 'offline' if status in (1, 3) else 'unknown'


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


def _huya_status_value(value: object) -> str:
    value = str(value or '').strip().upper()
    return 'live' if value == 'ON' else 'offline' if value in ('OFF', 'REPLAY') else 'unknown'


def _parse_huya_profile_observations(payload: object) -> list[_HuyaStatusObservation]:
    if not isinstance(payload, dict):
        return []
    data = payload.get('data')
    if payload.get('status') != 200 or not isinstance(data, dict):
        return []

    observations = []
    real_status = _huya_status_value(data.get('realLiveStatus'))
    if real_status != 'unknown':
        observations.append(_HuyaStatusObservation(
            real_status, 'profile.realLiveStatus', real_live_status=True,
        ))
    live_status = _huya_status_value(data.get('liveStatus'))
    if live_status != 'unknown':
        observations.append(_HuyaStatusObservation(live_status, 'profile.liveStatus'))
    return observations


def _fetch_huya_profile_status(room_id: str,
                               deadline: float) -> list[_HuyaStatusObservation]:
    referer = _HUYA_ROOM_ENDPOINT.format(room_id=room_id)
    response = requests.get(
        _HUYA_PROFILE_ENDPOINT,
        params={
            'm': 'Live',
            'do': 'profileRoom',
            'roomid': room_id,
            'showSecret': '1',
        },
        headers={
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': referer,
            'User-Agent': _HUYA_USER_AGENT,
            'xweb_xhr': '1',
        },
        timeout=_remaining_timeout(
            deadline,
            connect=HUYA_STATUS_CONNECT_TIMEOUT_SECONDS,
            read=HUYA_STATUS_READ_TIMEOUT_SECONDS,
        ),
    )
    response.raise_for_status()
    observations = _parse_huya_profile_observations(response.json())
    if not observations:
        raise LiveRoomError('虎牙轻量接口未包含可识别的状态')
    return observations


def _fetch_huya_desktop_status(room_id: str,
                               deadline: float) -> list[_HuyaStatusObservation]:
    room_url = _HUYA_ROOM_ENDPOINT.format(room_id=room_id)
    response = requests.get(
        room_url,
        headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://www.huya.com/',
            'User-Agent': _HUYA_USER_AGENT,
        },
        timeout=_remaining_timeout(
            deadline,
            connect=HUYA_STATUS_CONNECT_TIMEOUT_SECONDS,
            read=HUYA_STATUS_READ_TIMEOUT_SECONDS,
        ),
    )
    response.raise_for_status()
    status = _parse_huya_page_status(response.text)
    if status == 'unknown':
        raise LiveRoomError('虎牙桌面页未包含可识别的状态')
    return [_HuyaStatusObservation(status, 'desktop')]


def _fetch_huya_mobile_status(room_id: str,
                              deadline: float) -> list[_HuyaStatusObservation]:
    room_url = _HUYA_MOBILE_ROOM_ENDPOINT.format(room_id=room_id)
    response = requests.get(
        room_url,
        headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Referer': 'https://m.huya.com/',
            'User-Agent': _HUYA_MOBILE_USER_AGENT,
        },
        timeout=_remaining_timeout(
            deadline,
            connect=HUYA_STATUS_CONNECT_TIMEOUT_SECONDS,
            read=HUYA_STATUS_READ_TIMEOUT_SECONDS,
        ),
    )
    response.raise_for_status()
    status = _parse_huya_mobile_page_status(response.text)
    if status == 'unknown':
        raise LiveRoomError('虎牙移动页未包含可识别的状态')
    return [_HuyaStatusObservation(status, 'mobile')]


def _resolve_huya_observations(room_id: str,
                               observations: list[_HuyaStatusObservation]) -> str:
    if not observations:
        return 'unknown'
    distinct_statuses = {item.status for item in observations}
    real_statuses = [item for item in observations if item.real_live_status]
    if real_statuses:
        selected = real_statuses[0]
    else:
        selected = next(
            (item for item in observations if item.status == 'live'),
            observations[0],
        )
    if len(distinct_statuses) > 1:
        source_states = ', '.join(f'{item.source}={item.status}' for item in observations)
        logger.warning(
            f'虎牙直播状态来源冲突 room_id={room_id} '
            f'sources=[{source_states}] selected={selected.source}:{selected.status}'
        )
    return selected.status


def _get_huya_live_status(room_id: str, timeout: Optional[float] = None,
                          deadline: Optional[float] = None) -> str:
    """Race Huya's JSON, desktop, and mobile sources within one deadline."""
    deadline = _request_deadline(timeout, deadline)
    executor = ThreadPoolExecutor(max_workers=3)
    futures = {}
    observations = []
    errors = {}

    def collect(future) -> None:
        source = futures[future]
        try:
            observations.extend(future.result())
        except Exception as exc:
            errors[source] = str(exc)

    def resolve_and_watch(pending_futures=()) -> str:
        status = _resolve_huya_observations(room_id, observations)

        def log_late_conflict(future) -> None:
            try:
                late_observations = future.result()
            except Exception:
                return
            conflicting = [item for item in late_observations if item.status != status]
            if conflicting:
                source_states = ', '.join(
                    f'{item.source}={item.status}' for item in conflicting
                )
                logger.warning(
                    f'虎牙直播状态来源冲突 room_id={room_id} '
                    f'late_sources=[{source_states}] selected={status}'
                )

        for future in pending_futures:
            future.add_done_callback(log_late_conflict)
        return status

    try:
        hedge_at = time.monotonic() + HUYA_FALLBACK_HEDGE_SECONDS
        profile_future = executor.submit(_fetch_huya_profile_status, room_id, deadline)
        futures[profile_future] = 'profile'
        hedge_timeout = min(
            max(0.0, hedge_at - time.monotonic()),
            max(0.0, deadline - time.monotonic()),
        )
        try:
            observations.extend(profile_future.result(timeout=hedge_timeout))
            return resolve_and_watch()
        except FuturesTimeoutError:
            pass
        except Exception as exc:
            errors['profile'] = str(exc)

        # Keep the JSON source's head start even when it fails quickly. This
        # bounds the normal request rate against the two heavier HTML pages.
        fallback_delay = min(
            max(0.0, hedge_at - time.monotonic()),
            max(0.0, deadline - time.monotonic()),
        )
        if fallback_delay:
            time.sleep(fallback_delay)

        desktop_future = executor.submit(_fetch_huya_desktop_status, room_id, deadline)
        mobile_future = executor.submit(_fetch_huya_mobile_status, room_id, deadline)
        futures[desktop_future] = 'desktop'
        futures[mobile_future] = 'mobile'
        pending = {future for future in futures if not future.done()}
        for future in futures:
            if future.done() and not (
                future is profile_future and 'profile' in errors
            ):
                collect(future)

        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = wait(pending, timeout=remaining, return_when=FIRST_COMPLETED)
            if not done:
                break
            for future in done:
                collect(future)

            # realLiveStatus is definitive. Once the JSON request has also
            # completed, any live observation wins over non-real conflicts.
            if any(item.real_live_status for item in observations):
                return resolve_and_watch(pending)
            if profile_future.done() and any(item.status == 'live' for item in observations):
                return resolve_and_watch(pending)

        status = resolve_and_watch(pending)
        if status != 'unknown':
            return status
        error_summary = '; '.join(f'{source}: {error}' for source, error in errors.items())
        raise LiveRoomError(f'虎牙三个状态来源均失败 ({error_summary or "查询超时"})')
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def get_live_status(platform_code: str, room_id: str,
                    timeout: Optional[float] = None,
                    deadline: Optional[float] = None,
                    force_refresh: bool = False) -> dict:
    """Return a best-effort live state without allowing upstream errors to escape."""
    platform_code = (platform_code or '').strip().upper()
    room_id = (room_id or '').strip()
    supported = platform_code in _STATUS_ENDPOINTS
    result = {
        'platform': platform_code,
        'status': 'unknown',
        'supported': supported,
        'stale': False,
    }
    if not supported or not room_id:
        return result

    cache_key = f'{platform_code}:{room_id}'
    if not force_refresh:
        cached = _cached_live_status(cache_key)
        if cached is not None:
            return cached

    # The per-room lock turns the process-local cache into a single-flight
    # cache when overlapping API requests ask for the same room.
    with _live_status_key_lock(cache_key):
        if not force_refresh:
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
            logger.warning(
                f'查询直播状态失败 platform={platform_code} room_id={room_id}: {exc}'
            )

        if result['status'] != 'unknown':
            if platform_code == 'HUYA':
                _store_last_good_status(cache_key, result)
            ttl = LIVE_STATUS_CACHE_SECONDS
        else:
            last_good = _last_good_status(cache_key) if platform_code == 'HUYA' else None
            if last_good is not None:
                result = last_good
                result['stale'] = True
            ttl = LIVE_STATUS_FAILURE_CACHE_SECONDS
        _store_live_status(cache_key, result, ttl)
        return result.copy()


def _resolved_live_rooms(live_rooms: dict[str, str]) -> dict[str, Optional[dict]]:
    """Normalize configured room URLs without performing network requests."""
    resolved = {}
    for player_id, live_url in (live_rooms or {}).items():
        try:
            room = normalize_live_room('', live_url)
        except LiveRoomError:
            resolved[str(player_id)] = None
            continue
        if room.get('room_id'):
            resolved[str(player_id)] = room
    return resolved


def get_cached_live_statuses(live_rooms: dict[str, str]) -> dict[str, dict]:
    """Read scheduled statuses only; a missing cache entry means offline."""
    resolved = _resolved_live_rooms(live_rooms)
    statuses = {}
    room_statuses = {}
    for player_id, room in resolved.items():
        if not room:
            statuses[player_id] = {
                'platform': '',
                'status': 'offline',
                'supported': False,
                'stale': False,
            }
            continue
        room_key = f"{room['platform']}:{room['room_id']}"
        if room_key not in room_statuses:
            # The scheduler runs in another process, so Redis is authoritative.
            # The local value is only a development fallback when Redis is absent.
            cached = _shared_cache_get(_shared_status_cache_key(room_key))
            if cached is None:
                with _live_status_cache_lock:
                    item = _live_status_cache.get(room_key)
                    cached = item[1].copy() if item and item[0] > time.monotonic() else None
            room_statuses[room_key] = cached or {
                'platform': room['platform'],
                'status': 'offline',
                'supported': room['platform'] in _STATUS_ENDPOINTS,
                'stale': False,
            }
        statuses[player_id] = room_statuses[room_key].copy()
    return statuses


def get_live_statuses(live_rooms: dict[str, str], *, force_refresh=False) -> dict[str, dict]:
    """Refresh several configured rooms concurrently for scheduled jobs."""
    resolved = _resolved_live_rooms(live_rooms)

    if not resolved:
        return {}

    room_players = {}
    unique_rooms = {}
    for player_id, room in resolved.items():
        if not room:
            continue
        room_key = f"{room['platform']}:{room['room_id']}"
        unique_rooms.setdefault(room_key, room)
        room_players.setdefault(room_key, []).append(player_id)
    if not unique_rooms:
        return {}

    statuses = {}
    deadline = time.monotonic() + LIVE_STATUS_BATCH_BUDGET_SECONDS
    with ThreadPoolExecutor(max_workers=min(6, len(unique_rooms))) as executor:
        futures = {
            executor.submit(
                get_live_status,
                room['platform'],
                room['room_id'],
                deadline=deadline,
                force_refresh=force_refresh,
            ): room_key
            for room_key, room in unique_rooms.items()
        }
        for future in as_completed(futures):
            room_key = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # Guard the batch if a future provider is added incorrectly.
                logger.warning(f'批量查询直播状态失败 room={room_key}: {exc}')
                result = {
                    'platform': unique_rooms[room_key]['platform'],
                    'status': 'unknown',
                    'supported': False,
                    'stale': False,
                }
            for player_id in room_players[room_key]:
                statuses[player_id] = result.copy()
    return statuses
