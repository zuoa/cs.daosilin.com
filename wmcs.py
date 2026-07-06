import math
import time

import requests

from ajlog import logger


import re
# Steam 的 64 位基准值（Universe 1 的偏移量）
STEAM_ID64_BASE = 76561197960265728
def to_steamid64(steamid: str) -> int:
    """
    将各种格式的 SteamID 转换为 SteamID64（17 位整数）。

    支持的输入格式：
    - SteamID2:  STEAM_0:1:12345678  或  STEAM_1:1:12345678
    - SteamID3:  [U:1:24691357]
    - AccountID: 24691357（纯数字 32 位账户 ID）
    - SteamID64: 76561197984931085（已经是 64 位，直接返回）

    返回：
    - int：对应的 SteamID64

    异常：
    - ValueError：格式无法识别时抛出
    """
    steamid = str(steamid).strip()

    # ── 已经是 SteamID64（17 位纯数字）──
    if re.fullmatch(r'\d{17}', steamid):
        return int(steamid)

    # ── SteamID2：STEAM_X:Y:Z ──
    m = re.fullmatch(r'STEAM_\d:([01]):(\d+)', steamid, re.IGNORECASE)
    if m:
        auth_bit = int(m.group(1))   # Y，0 或 1
        account_id_half = int(m.group(2))   # Z
        account_id = account_id_half * 2 + auth_bit
        return STEAM_ID64_BASE + account_id

    # ── SteamID3：[U:1:N] ──
    m = re.fullmatch(r'\[U:1:(\d+)\]', steamid, re.IGNORECASE)
    if m:
        account_id = int(m.group(1))
        return STEAM_ID64_BASE + account_id

    # ── 纯数字（32 位 AccountID）──
    if re.fullmatch(r'\d{1,10}', steamid):
        account_id = int(steamid)
        return STEAM_ID64_BASE + account_id

    raise ValueError(f"无法识别的 SteamID 格式：{steamid!r}")

class WMAPI:
    API_GET_MATCH = 'https://api.wmpvp.com/api/v1/csgo/match'
    API_GET_MATCH_LIST = 'https://api.wmpvp.com/api/csgo/home/match/list'

    def __init__(self, token, token_steam_id, app_version='3.6.6.192', device='kGPSJ1758528365nD8AvNa9iI0'):
        self._token = token
        self._token_steam_id = token_steam_id
        self._app_version = app_version
        self._device = device
        self._headers = {
            'User-Agent': f'Mozilla/5.0 (Linux; Android 15; V2417A Build/AP3A.240905.015.A2; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/138.0.7204.179 Mobile Safari/537.36 EsportsApp Version={self._app_version}',
            'appversion': self._app_version,
            'device': self._device,
            'accessToken': self._token,
            'platform': 'h5_android',
            'Referer': 'https://news.wmpvp.com/'
        }

    def _post(self, url, data, headers=None):
        if headers:
            headers = {**self._headers, **headers}
        else:
            headers = self._headers
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                return response.json().get('data', None)
            else:
                logger.warning(f"WMAPI: 请求失败，状态码 {response.status_code}")
                return None
        except requests.RequestException as e:
            logger.warning(f"WMAPI: 请求异常 {e}")
            return None

    def get_match_list(self, player_steam_id, total=10):
        headers = {
            "t": str(math.floor(time.time() / 1000)),
            "gameType": "2",
            "gameTypeStr": "2",
        }

        all_matches = []
        pages = math.ceil(total / 10)
        for page in range(1, pages + 1):
            match_list_data = self._post(self.API_GET_MATCH_LIST, {
                "mySteamId": self._token_steam_id,
                "toSteamId": player_steam_id,
                "csgoSeasonId": "recent",
                "pvpType": -1,
                "page": page,
                "pageSize": 10,
                "dataSource": 3
            }, headers=headers)

            match_list = match_list_data.get('matchList', [])
            if not match_list:
                break
            all_matches.extend(match_list)
            if len(all_matches) >= total:
                break

        return all_matches

    def get_match(self, match_id):
        return self._post(self.API_GET_MATCH, {
            "matchId": match_id,
            "platform": "admin",
            "dataSource": "3"
        })


if __name__ == '__main__':
    wm = WMAPI(token='c27dd7695e6913c414a018601470e48426c96805', token_steam_id='76561198256708927')
    match_list_data = wm.get_match_list( to_steamid64("1079185706"))
    print(match_list_data)
    for match in match_list_data:
        match_id = match.get('matchId')

        print(match)
        match_data = wm.get_match(match_id)
        print(match_data)
