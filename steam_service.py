"""Steam public-profile helpers."""
import re
from urllib.parse import urlsplit
from xml.etree import ElementTree

import requests


class SteamAvatarError(ValueError):
    pass


def normalize_steam_id(value: str) -> str:
    value = (value or '').strip()
    if re.fullmatch(r'\d{17}', value):
        return value
    match = re.fullmatch(r'STEAM_\d:([01]):(\d+)', value, re.IGNORECASE)
    if match:
        return str(76561197960265728 + int(match.group(2)) * 2 + int(match.group(1)))
    match = re.fullmatch(r'\[U:1:(\d+)\]', value, re.IGNORECASE)
    if match:
        return str(76561197960265728 + int(match.group(1)))
    if re.fullmatch(r'\d{1,10}', value):
        return str(76561197960265728 + int(value))
    raise SteamAvatarError('请填写有效的 Steam ID')


def fetch_steam_avatar(steam_id: str, timeout: int = 8) -> dict:
    steam_id64 = normalize_steam_id(steam_id)
    try:
        response = requests.get(
            f'https://steamcommunity.com/profiles/{steam_id64}',
            params={'xml': '1'},
            headers={'Accept': 'application/xml', 'User-Agent': 'cs.daosilin.com/1.0'},
            timeout=timeout,
        )
        response.raise_for_status()
        root = ElementTree.fromstring(response.content)
    except (requests.RequestException, ElementTree.ParseError) as exc:
        raise SteamAvatarError('获取 Steam 个人资料失败，请稍后重试') from exc

    avatar = (root.findtext('avatarFull') or '').strip()
    parsed = urlsplit(avatar)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        raise SteamAvatarError('未找到该 Steam 玩家的公开头像')
    return {'steam_id': steam_id64, 'avatar': avatar}
