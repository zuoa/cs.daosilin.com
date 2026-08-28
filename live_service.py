"""Live-room URL normalization and public profile lookup helpers."""
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

import requests


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
