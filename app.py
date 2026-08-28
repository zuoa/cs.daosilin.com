import os
import secrets
import threading
from datetime import datetime
from urllib.parse import urlsplit

from flask import Flask, request, send_from_directory
from flask_caching import Cache

import title_service
from ajlog import logger
from auth import (captcha_ok, captcha_response, clear_login_fail, current_admin,
                  EXTERNAL_TOKEN_MIN_LENGTH, external_api_token_required,
                  external_api_token_status, login_admin, login_locked, logout_admin,
                  record_login_fail,
                  revoke_database_external_api_token, save_external_api_token,
                  verify_password)
from champion_service import judge_champion
from config import (ADMIN_PASSWORD, ADMIN_USERNAME, EXTERNAL_API_TOKEN, REDIS_URL,
                    SECRET_KEY, SITE_NAME)
from database import (AdminUser, MatchPlayer, Player, CupDayChampion, create_tables, Config, PlayerTitle,
                      Match, Season, SeasonRoster, MatchSelection, import_history_sql)
from scheduler import (crawl_season_with_status, get_crawl_status,
                       crawl_is_running, is_auto_crawl_enabled, season_crawl_phase,
                       set_auto_crawl_enabled, set_crawl_status)
from title_service import title_service
from utils import success, error

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['EXTERNAL_API_TOKEN'] = EXTERNAL_API_TOKEN

if REDIS_URL:
    cache = Cache(config={
        'CACHE_TYPE': 'RedisCache',
        'CACHE_REDIS_URL': REDIS_URL,
        'CACHE_DEFAULT_TIMEOUT': 60,
        'CACHE_KEY_PREFIX': 'cs:',
    })
else:
    cache = Cache(config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 60})
cache.init_app(app)

try:
    create_tables()
except Exception as e:
    logger.error(f"启动时初始化数据库失败: {e}")


@app.before_request
def protect_admin():
    path = request.path
    public_api = {'/api/admin/login', '/api/admin/captcha', '/api/admin/logout'}
    if path in public_api:
        return None
    if path.startswith('/api/admin') and not current_admin():
        return error(401, "未登录"), 401
    return None


def _season_list_payload():
    seasons = Season.get_all() or []
    for s in seasons:
        Season.annotate(s)
        cup = s.get('cup_name')
        s['match_count'] = Match.select().where(Match.cup_name == cup).count() if cup else 0
        s['day_count'] = len(MatchPlayer.get_cup_day_set(cup) or [])
        for key in ('created_at', 'updated_at', 'start_date', 'end_date'):
            val = s.get(key)
            if isinstance(val, datetime):
                s[key] = val.isoformat(timespec='seconds')
    seasons.sort(key=lambda x: (
        0 if x.get('status') == 'active' else 1,
        x.get('start_date') or '',
        x.get('cup_name') or '',
    ), reverse=True)
    return seasons


def _build_cup_players(cup, day=None):
    all_players = Player.get_all()
    all_players_map = {player["player_id"]: player for player in all_players}
    day_champion = CupDayChampion.get_champion_by_cup_and_day(cup, day)
    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))

    filter_params = {'cup_name': cup}
    if day is not None:
        filter_params['play_day'] = day
    players = MatchPlayer.filter_records(**filter_params)
    players_map = {player["player_id"]: {
        "nickname": player["nickname"],
        "avatar": player["avatar"],
        "player_id": player["player_id"],
        "alias_name": all_players_map.get(player["player_id"], {}).get("alias_name", ""),
        "team_name": player.get("team_name", ""),
        "is_champion": player["player_id"] in day_champion.get("champion_team_player_ids", '').split(
            ',') if day_champion else False,
        "is_runner_up": player["player_id"] in day_champion.get("runner_up_team_player_ids", '').split(
            ',') if day_champion else False,
    } for player in players}

    player_data = []
    for player_id, player in players_map.items():
        d = MatchPlayer.get_match_exploit(cup, player_id, day)
        if d:
            player.update(d)
        for champion in all_champions:
            if player_id in champion.get("champion_team_player_ids", '').split(','):
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('champion_team_name'),
                    'trophy': 'champion',
                })
            if player_id in champion.get("runner_up_team_player_ids", '').split(','):
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('runner_up_team_name'),
                    'trophy': 'runner_up',
                })
        player_data.append(player)
    player_data.sort(key=lambda x: x.get('avg_pw_rating', 0), reverse=True)
    if day:
        comparable_players = [player for player in player_data if player.get('match_count')]
        for player in comparable_players:
            player['titles'] = title_service.build_title_rows(player, comparable_players)
    else:
        for player in player_data:
            player['titles'] = PlayerTitle.get_player_titles(player['player_id'], cup, day)
    return player_data, MatchPlayer.get_cup_day_set(cup)


def _player_detail_payload(player_id, cup, day=None):
    rec = Player.get_or_none(Player.player_id == player_id)
    if not rec:
        return None, "选手不存在"
    player = rec.to_dict()
    for key in ('created_at', 'updated_at'):
        if hasattr(player.get(key), 'isoformat'):
            player[key] = player[key].isoformat()
    player_data = MatchPlayer.get_match_exploit(cup, player_id, day)
    if not player_data:
        return None, "该选手在此杯赛/日期下无数据"
    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))
    trophy_history = []
    for champion in all_champions:
        if player_id in champion.get("champion_team_player_ids", '').split(','):
            trophy_history.append({
                'day': champion.get('day'),
                'team_name': champion.get('champion_team_name'),
                'trophy': 'champion',
            })
        if player_id in champion.get("runner_up_team_player_ids", '').split(','):
            trophy_history.append({
                'day': champion.get('day'),
                'team_name': champion.get('runner_up_team_name'),
                'trophy': 'runner_up',
            })
    cup_days = MatchPlayer.get_cup_day_set(cup)
    historical_data = []
    for historical_day in cup_days:
        day_data = MatchPlayer.get_match_exploit(cup, player_id, historical_day)
        if day_data:
            historical_data.append({'day': historical_day, 'data': day_data})
    all_players_data = []
    for p in Player.get_all():
        p_data = MatchPlayer.get_match_exploit(cup, p["player_id"], day)
        if p_data:
            p_data['player_id'] = p["player_id"]
            p_data['nickname'] = p["nickname"]
            all_players_data.append(p_data)
    comparison_player = next(
        (data for data in all_players_data if data['player_id'] == player_id),
        None,
    )
    if comparison_player:
        comparison_player['day_history'] = [item['data'] for item in historical_data]
        titles = title_service.build_title_rows(comparison_player, all_players_data)
    else:
        titles = []
    player_rankings = {}
    for field in ['avg_pw_rating', 'total_kills', 'kd_ratio', 'win_rate', 'avg_adpr', 'total_mvp']:
        if field in player_data:
            sorted_players = sorted(all_players_data, key=lambda x: x.get(field, 0), reverse=True)
            try:
                player_rankings[field] = next(
                    i for i, p in enumerate(sorted_players) if p['player_id'] == player_id) + 1
            except StopIteration:
                player_rankings[field] = len(all_players_data)
    match_records = MatchPlayer.get_player_match_records(cup, player_id, day)
    for record in match_records:
        record['start_time'] = _iso_dt(record.get('start_time'))
        record['end_time'] = _iso_dt(record.get('end_time'))
        record['mvp'] = bool(record.get('mvp'))

    return {
        'player': player,
        'player_data': player_data,
        'titles': titles,
        'trophy_history': trophy_history,
        'historical_data': historical_data,
        'player_rankings': player_rankings,
        'map_stats': MatchPlayer.get_player_map_stats(cup, player_id, day),
        'match_records': match_records,
        'cup': cup,
        'cup_alias': Season.display_name(cup),
        'day': day,
        'cup_days': cup_days,
        'last_crawl_time': Config.get_value("last_crawl_time"),
    }, None


@app.route('/api/v1/meta')
def api_meta():
    return success({'site_name': SITE_NAME, 'admin_user': current_admin()})


@app.route('/api/v1/seasons')
@cache.cached(timeout=60)
def api_seasons():
    return success({
        'seasons': _season_list_payload(),
        'last_crawl_time': Config.get_value("last_crawl_time"),
        'site_name': SITE_NAME,
    })


@app.route('/api/v1/cup/<string:cup>')
@cache.cached(timeout=60, query_string=True)
def api_cup(cup):
    day = request.args.get('day') or None
    players, cup_days = _build_cup_players(cup, day)
    return success({
        'cup': cup,
        'cup_alias': Season.display_name(cup),
        'day': day,
        'cup_days': cup_days,
        'players': players,
        'last_crawl_time': Config.get_value("last_crawl_time"),
    })


@app.route('/api/v1/player/<string:player_id>')
@cache.cached(timeout=60, query_string=True)
def api_player_detail(player_id):
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    day = request.args.get('day') or None
    payload, err = _player_detail_payload(player_id, cup, day)
    if err:
        return error(404, err)
    return success(payload)


@app.route('/api/v1/players')
@cache.cached(timeout=120, query_string=True)
def api_players():
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")

    day = request.args.get('day')

    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))

    all_players = Player.get_all()
    for i in range(len(all_players)):
        player = all_players[i]
        player_id = player.get('player_id')
        d = MatchPlayer.get_match_exploit(cup, player_id, day)
        if d:
            player.update(d)

        for champion in all_champions:
            if player_id in champion.get("champion_team_player_ids", '').split(','):
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('champion_team_name'),
                    'trophy': 'champion',
                })
            if player_id in champion.get("runner_up_team_player_ids", '').split(','):
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('runner_up_team_name'),
                    'trophy': 'runner_up',
                })
    last_crawl_time = Config.get_value("last_crawl_time")
    return success({"players": all_players, "cache_time": last_crawl_time})


def _external_season_payload(season):
    return {
        'cup_name': season.get('cup_name'),
        'name': season.get('cup_alias') or season.get('name') or season.get('cup_name'),
        'start_date': _iso_dt(season.get('start_date')),
        'end_date': _iso_dt(season.get('end_date')),
        'status': season.get('status'),
        'match_type': season.get('match_type'),
    }


def _resolve_external_seasons(selector):
    seasons = list(Season.select().order_by(Season.end_date.desc()).dicts())
    normalized = (selector or 'last').strip()
    if normalized.lower() == 'all':
        return seasons, None
    if normalized.lower() == 'last':
        now = datetime.now()
        completed = [
            season for season in seasons
            if season.get('status') == 'archived' or season.get('end_date') <= now
        ]
        return completed[:1], None if completed else "暂无已结束的赛季"

    exact = [
        season for season in seasons
        if normalized in (season.get('cup_name'), season.get('cup_alias'), season.get('name'))
    ]
    if exact:
        return exact[:1], None
    folded = normalized.casefold()
    insensitive = [
        season for season in seasons
        if folded in {
            str(season.get('cup_name') or '').casefold(),
            str(season.get('cup_alias') or '').casefold(),
            str(season.get('name') or '').casefold(),
        }
    ]
    return (insensitive[:1], None) if insensitive else ([], "赛季不存在")


@app.route('/api/v1/external/players', defaults={'season_selector': None})
@app.route('/api/v1/external/players/<path:season_selector>')
@external_api_token_required
def api_external_players(season_selector):
    """Token-protected player statistics for all, last, or a named season."""
    selector = season_selector if season_selector is not None else request.args.get('season', 'last')
    seasons, err = _resolve_external_seasons(selector)
    if err:
        return error(404, err), 404

    players = MatchPlayer.get_external_player_stats([
        season['cup_name'] for season in seasons
    ])
    response = success({
        'selector': (selector or 'last').strip(),
        'seasons': [_external_season_payload(season) for season in seasons],
        'player_count': len(players),
        'players': players,
        'last_crawl_time': Config.get_value('last_crawl_time'),
    })
    response.headers['Cache-Control'] = 'private, no-store'
    return response


def _external_lookup_arg(*names):
    """Read aliases for one lookup argument and reject conflicting values."""
    values = []
    for name in names:
        value = (request.args.get(name) or '').strip()
        if value and value not in values:
            values.append(value)
    if len(values) > 1:
        raise ValueError
    return values[0] if values else ''


@app.route('/api/v1/external/player')
@external_api_token_required
def api_external_player():
    """Token-protected stats for one player resolved by Steam ID or room ID."""
    try:
        steam_id = _external_lookup_arg('steam_id', 'steamid', 'STEAMID')
        room_id = _external_lookup_arg('room_id', 'roomid', 'room')
    except ValueError:
        return error(400, "同一查询参数不能提供多个不同值"), 400
    if bool(steam_id) == bool(room_id):
        return error(400, "请且仅请提供 steam_id 或 room_id 其中一个参数"), 400

    player = Player.find_by_external_identifier(steam_id=steam_id, room_id=room_id)
    if not player:
        return error(404, "选手不存在"), 404

    selector = request.args.get('season', 'last')
    seasons, err = _resolve_external_seasons(selector)
    if err:
        return error(404, err), 404
    players = MatchPlayer.get_external_player_stats(
        [season['cup_name'] for season in seasons],
        player_id=player.player_id,
    )
    if not players:
        return error(404, "该选手在所选赛季中无数据"), 404

    lookup_type = 'steam_id' if steam_id else 'room_id'
    response = success({
        'lookup': {'type': lookup_type, 'value': steam_id or room_id},
        'selector': (selector or 'last').strip(),
        'seasons': [_external_season_payload(season) for season in seasons],
        'player': players[0],
        'last_crawl_time': Config.get_value('last_crawl_time'),
    })
    response.headers['Cache-Control'] = 'private, no-store'
    return response


@app.route('/api/admin/champion/judge')
def api_admin_champion_judge():
    day = request.args.get('day')
    if day is None:
        return error(400, "参数 day 不能为空")

    cup_name = request.args.get('cup')
    if not cup_name:
        return error(400, "参数 cup 不能为空")
    season = Season.get_by_cup(cup_name)
    if season and not season.get('champion_enabled'):
        return error(409, "该赛季未启用冠军统计")

    try:
        judge_champion(day, cup_name)
    except Exception as e:
        logger.error(f"计算冠军和亚军失败: {str(e)}")

    return success("计算冠军和亚军任务已触发")


@app.route('/api/admin/title/refresh')
def api_admin_title_refresh():
    day = request.args.get('day')
    cup_name = request.args.get('cup')
    if not cup_name:
        return error(400, "参数 cup 不能为空")

    try:
        # 计算整个杯赛的称号
        is_success = title_service.calculate_and_save_titles(cup_name)
        if is_success:
            logger.info(f"成功计算 {cup_name} 的称号")
        else:
            logger.error(f"计算 {cup_name} 称号失败")

        if day:
            is_success = title_service.calculate_and_save_titles(cup_name, day)
            if is_success:
                logger.info(f"成功计算 {cup_name} {day} 的称号")
            else:
                logger.error(f"计算 {cup_name} {day} 称号失败")

    except Exception as e:
        logger.error(f"计算称号失败: {str(e)}")

    return success("计算称号任务已触发")


# ==================== 赛季采集 / 玩家库 / 比赛纳入剔除 ====================

_crawl_lock = threading.Lock()
_crawl_running = set()


def _admin_authed():
    return bool(current_admin())


def _parse_ids(raw):
    return [p.strip() for p in (raw or '').replace(';', ',').replace('\n', ',').split(',') if p.strip()]


def _parse_optional_http_url(raw, max_length=500):
    value = (raw or '').strip()
    if not value:
        return None
    parsed = urlsplit(value)
    if len(value) > max_length or parsed.scheme.lower() not in ('http', 'https') or not parsed.netloc:
        raise ValueError
    return value


def _parse_hit_ratio():
    raw = request.args.get('hit_ratio')
    if raw in (None, ''):
        raw = request.args.get('hit_percent')
        if raw in (None, ''):
            return 0.6
        try:
            return max(0.0, min(1.0, float(raw) / 100.0))
        except ValueError:
            return 0.6
    try:
        value = float(raw)
    except ValueError:
        return 0.6
    if value > 1:
        value = value / 100.0
    return max(0.0, min(1.0, value))


def _parse_season_datetime(raw):
    """解析 datetime-local 值，数据库使用 DateTimeField 保存。"""
    value = (raw or '').strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%dT%H:%M:%S')
    except ValueError as exc:
        raise ValueError('时间格式应为 YYYY-MM-DDTHH:MM:SS') from exc


def _selection_payload(cup, status=None, day=None):
    selections = MatchSelection.list_by_season(cup, status=status, play_day=day)
    match_ids = [s['match_id'] for s in selections]
    match_map = {m.match_id: m.to_dict()
                 for m in Match.select().where(Match.match_id.in_(match_ids))} if match_ids else {}
    library_set = set(Player.get_library_ids())
    players_by_match = {}
    if match_ids:
        for mp in MatchPlayer.select().where(MatchPlayer.match_id.in_(match_ids)):
            players_by_match.setdefault(mp.match_id, []).append({
                'player_id': mp.player_id,
                'nickname': mp.nickname,
                'team': mp.team,
                'in_library': mp.player_id in library_set,
            })
    result = []
    for s in selections:
        m = match_map.get(s['match_id'], {})
        result.append({
            'match_id': s['match_id'],
            'play_day': s['play_day'],
            'roster_hit_count': s['roster_hit_count'],
            'status': s['status'],
            'start_time': _iso_dt(m.get('start_time')),
            'end_time': _iso_dt(m.get('end_time')),
            'map_name': m.get('map_name'),
            'game_mode': m.get('game_mode'),
            'team1_name': m.get('team1_name'),
            'team2_name': m.get('team2_name'),
            'team1_score': m.get('team1_score'),
            'team2_score': m.get('team2_score'),
            'players': players_by_match.get(s['match_id'], []),
        })
    result.sort(
        key=lambda item: (item.get('start_time') or item.get('play_day') or '', item.get('match_id') or ''),
        reverse=True,
    )
    return result


_MATCH_PLAYER_DETAIL_FIELDS = (
    'player_id', 'nickname', 'avatar', 'team', 'team_name',
    'kill', 'death', 'assist', 'rating', 'pw_rating', 'adpr', 'kast',
    'headshot', 'headshot_ratio', 'entry_kill', 'first_death',
    'mvp', 'two_kill', 'three_kill', 'four_kill', 'five_kill',
    'awp_kill', 'rws', 'damage', 'flash', 'flash_success',
    'vs2', 'vs3', 'vs4', 'vs5', 'win',
)


def _iso_dt(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec='seconds')
    return value


def _match_detail_payload(cup, match_id):
    sel = MatchSelection.get_by_match(match_id, cup)
    if not sel:
        return None
    match = Match.get_by_match_id(match_id) or {}
    library_set = set(Player.get_library_ids())
    player_rows = list(MatchPlayer.select().where(MatchPlayer.match_id == match_id))
    player_ids = [row.player_id for row in player_rows]
    alias_map = {}
    if player_ids:
        for rec in Player.select().where(Player.player_id.in_(player_ids)):
            alias_map[rec.player_id] = rec.alias_name
    players = []
    for row in player_rows:
        item = {field: getattr(row, field, None) for field in _MATCH_PLAYER_DETAIL_FIELDS}
        item['in_library'] = row.player_id in library_set
        item['alias_name'] = alias_map.get(row.player_id) or ''
        players.append(item)
    players.sort(key=lambda p: (
        p.get('team') or 99,
        -(p.get('pw_rating') or p.get('rating') or 0),
    ))
    return {
        'match_id': match_id,
        'play_day': sel.get('play_day') or match.get('play_day'),
        'roster_hit_count': sel.get('roster_hit_count') or 0,
        'status': sel.get('status'),
        'source_type': sel.get('source_type'),
        'start_time': _iso_dt(match.get('start_time')),
        'end_time': _iso_dt(match.get('end_time')),
        'duration': match.get('duration'),
        'map_name': match.get('map_name'),
        'map_name_en': match.get('map_name_en'),
        'map_url': match.get('map_url'),
        'map_logo': match.get('map_logo'),
        'game_mode': match.get('game_mode'),
        'win_team': match.get('win_team'),
        'team1_name': match.get('team1_name'),
        'team1_logo': match.get('team1_logo'),
        'team1_score': match.get('team1_score'),
        'team1_half_score': match.get('team1_half_score'),
        'team1_extra_score': match.get('team1_extra_score'),
        'team2_name': match.get('team2_name'),
        'team2_logo': match.get('team2_logo'),
        'team2_score': match.get('team2_score'),
        'team2_half_score': match.get('team2_half_score'),
        'team2_extra_score': match.get('team2_extra_score'),
        'players': players,
    }


@app.route('/api/admin/season/list')
def api_admin_season_list():
    if not _admin_authed():
        return error(403, "无权限访问")
    seasons = Season.get_all()
    for s in seasons:
        for key in ('created_at', 'updated_at', 'start_date', 'end_date'):
            val = s.get(key)
            if isinstance(val, datetime):
                s[key] = val.isoformat(timespec='seconds')
        s['roster_count'] = len(SeasonRoster.get_player_ids(s['cup_name']))
        s['approved_count'] = (MatchSelection
                               .select()
                               .where(MatchSelection.season_cup_name == s['cup_name'],
                                      MatchSelection.status == 'approved')
                               .count())
        s['rejected_count'] = (MatchSelection
                               .select()
                               .where(MatchSelection.season_cup_name == s['cup_name'],
                                      MatchSelection.status == 'rejected')
                               .count())
        s['pending_count'] = s['approved_count']
        if is_auto_crawl_enabled(s['cup_name']) and season_crawl_phase(s) == 'expired':
            set_auto_crawl_enabled(s['cup_name'], False)
            set_crawl_status(s['cup_name'], state='expired', message='赛季已截止，自动采集已停止')
        s['crawl'] = get_crawl_status(s['cup_name'])
    return success({"seasons": seasons})


@app.route('/api/admin/season/save')
def api_admin_season_save():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    try:
        start_date = _parse_season_datetime(request.args.get('start_date'))
        end_date = _parse_season_datetime(request.args.get('end_date'))
    except ValueError:
        return error(400, "时间格式无效，请选择精确到秒的日期时间")
    if not start_date or not end_date:
        return error(400, "开始时间和结束时间不能为空")
    if start_date and end_date and start_date > end_date:
        return error(400, "结束时间不能早于开始时间")
    existing = Season.get_or_none(Season.cup_name == cup)
    champion_raw = request.args.get('champion_enabled')
    champion_enabled = (
        champion_raw.lower() in ('1', 'true', 'yes', 'on')
        if champion_raw is not None
        else bool(existing.champion_enabled) if existing else False
    )
    fields = {
        'name': request.args.get('cup_alias') or request.args.get('name'),
        'cup_alias': request.args.get('cup_alias') or request.args.get('name'),
        'match_type': request.args.get('match_type') or 'custom',
        'start_date': start_date,
        'end_date': end_date,
        'status': request.args.get('status') or 'active',
        'hit_ratio': _parse_hit_ratio(),
        'champion_enabled': champion_enabled,
    }
    if existing:
        Season.update(**fields).where(Season.cup_name == cup).execute()
    else:
        Season.create(cup_name=cup, **fields)
    saved_season = Season.get_by_cup(cup)
    if fields['status'] != 'active':
        set_auto_crawl_enabled(cup, False)
        set_crawl_status(cup, state='stopped', message='赛季已归档，自动采集已停止')
    elif season_crawl_phase(saved_season) == 'expired':
        set_auto_crawl_enabled(cup, False)
        set_crawl_status(cup, state='expired', message='赛季已截止，自动采集已停止')
    try:
        cache.clear()
    except Exception:
        pass
    return success("赛季已保存")


@app.route('/api/admin/season/delete', methods=['POST', 'DELETE'])
def api_admin_season_delete():
    if not _admin_authed():
        return error(403, "无权限访问")
    payload = request.get_json(silent=True) or {}
    cup = (payload.get('cup') or request.args.get('cup') or '').strip()
    if not cup:
        return error(400, "参数 cup 不能为空"), 400

    with _crawl_lock:
        if cup in _crawl_running or crawl_is_running(cup):
            return error(409, "该赛季正在采集，请等待本轮完成后再删除"), 409
        if not Season.get_by_cup(cup):
            return error(404, "赛季不存在"), 404
        set_auto_crawl_enabled(cup, False)
        deleted = Season.delete_with_related_data(cup)

    try:
        cache.clear()
    except Exception:
        pass
    logger.info(f"赛季 {cup} 已删除: {deleted}")
    return success({
        'message': '赛季已删除',
        'cup_name': cup,
        'deleted': deleted,
    })


@app.route('/api/admin/season/roster/get')
def api_admin_season_roster_get():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    roster = []
    for pid in SeasonRoster.get_player_ids(cup):
        p = Player.get_or_none(Player.player_id == pid)
        roster.append({
            'player_id': pid,
            'nickname': p.nickname if p else '',
            'alias_name': p.alias_name if p else '',
            'in_library': bool(p.in_library) if p else False,
        })
    return success({"roster": roster})


@app.route('/api/admin/season/roster/save')
def api_admin_season_roster_save():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    pids = _parse_ids(request.args.get('player_ids', ''))
    SeasonRoster.set_roster(cup, pids)
    return success(f"种子已保存（{len(pids)} 人）")


@app.route('/api/admin/season/crawl')
def api_admin_season_crawl():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    season = Season.get_by_cup(cup)
    if not season:
        return error(404, "赛季不存在")
    mode = request.args.get('mode') or 'auto'
    if mode not in ('auto', 'once'):
        return error(400, "参数 mode 只能是 auto 或 once")
    if mode == 'auto' and season.get('status') != 'active':
        return error(409, "已归档赛季不能启动采集")
    if mode == 'auto' and season_crawl_phase(season) == 'expired':
        set_auto_crawl_enabled(cup, False)
        set_crawl_status(cup, state='expired', message='赛季已截止，不能再启动采集')
        return error(409, "赛季已截止，不能再启动采集")
    if mode == 'auto' and is_auto_crawl_enabled(cup):
        return success("自动采集已在运行，将每 10 分钟获取一次")
    if crawl_is_running(cup):
        return error(409, "该赛季正在采集")
    if mode == 'auto':
        set_auto_crawl_enabled(cup, True)
        set_crawl_status(cup, state='scheduled', message='自动采集已启动，将每 10 分钟获取一次')
    else:
        set_crawl_status(cup, state='scheduled', message='手动采集已排队')
    with _crawl_lock:
        if cup in _crawl_running:
            return error(409, "该赛季正在采集")
        if not Season.get_by_cup(cup):
            return error(404, "赛季不存在"), 404
        _crawl_running.add(cup)

    def _run():
        try:
            crawl_season_with_status(cup, manual=(mode == 'once'))
        except Exception as e:
            logger.error(f"采集赛季 {cup} 失败: {e}")
        finally:
            with _crawl_lock:
                _crawl_running.discard(cup)

    threading.Thread(target=_run, daemon=True, name=f'crawl-{cup}').start()
    if mode == 'once':
        return success("手动采集已启动，本轮完成后自动停止")
    return success("自动采集已启动，将每 10 分钟获取一次，赛季截止后自动停止")


@app.route('/api/admin/season/crawl/status')
def api_admin_season_crawl_status():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    season = Season.get_by_cup(cup)
    if season and is_auto_crawl_enabled(cup) and season_crawl_phase(season) == 'expired':
        set_auto_crawl_enabled(cup, False)
        set_crawl_status(cup, state='expired', message='赛季已截止，自动采集已停止')
    running = cup in _crawl_running or crawl_is_running(cup)
    # crawl_is_running 可能刚刚恢复了崩溃遗留的状态，需要重新读取。
    status = get_crawl_status(cup)
    status['running'] = running
    status['auto_enabled'] = is_auto_crawl_enabled(cup)
    return success(status)


@app.route('/api/admin/selection/list')
def api_admin_selection_list():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    status = request.args.get('status') or 'approved'
    day = request.args.get('day')
    return success({"list": _selection_payload(cup, status=status, day=day)})


@app.route('/api/admin/selection/detail')
def api_admin_selection_detail():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    match_id = (request.args.get('match_id') or '').strip()
    if not cup:
        return error(400, "参数 cup 不能为空")
    if not match_id:
        return error(400, "参数 match_id 不能为空")
    payload = _match_detail_payload(cup, match_id)
    if not payload:
        return error(404, "未找到该比赛")
    return success(payload)


@app.route('/api/admin/selection/pending')
def api_admin_selection_pending():
    """兼容旧入口：返回已纳入比赛。"""
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    return success({"list": _selection_payload(cup, status='approved', day=request.args.get('day'))})


def _parse_match_ids():
    return _parse_ids(request.args.get('match_ids', ''))


def _set_selection_status(cup, match_ids, status):
    n = 0
    for mid in match_ids:
        sel = MatchSelection.get_or_none((MatchSelection.match_id == mid) &
                                         (MatchSelection.season_cup_name == cup))
        if not sel:
            continue
        if status == 'approved':
            Match.update(cup_name=cup).where(Match.match_id == mid).execute()
            MatchPlayer.update(cup_name=cup).where(MatchPlayer.match_id == mid).execute()
        else:
            current = Match.get_by_match_id(mid)
            if current and current.get('cup_name') == cup:
                Match.update(cup_name=None).where(Match.match_id == mid).execute()
                MatchPlayer.update(cup_name=None).where(MatchPlayer.match_id == mid).execute()
        sel.status = status
        sel.save()
        n += 1
    return n


@app.route('/api/admin/selection/approve')
def api_admin_selection_approve():
    """恢复纳入：写回 cup_name，进入统计。"""
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    match_ids = _parse_match_ids()
    if not match_ids:
        return error(400, "参数 match_ids 不能为空")
    n = _set_selection_status(cup, match_ids, 'approved')
    try:
        cache.clear()
    except Exception:
        pass
    return success(f"已恢复纳入 {n} 场比赛")


@app.route('/api/admin/selection/reject')
def api_admin_selection_reject():
    """剔除比赛：清空 cup_name，不进入统计。"""
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    match_ids = _parse_match_ids()
    if not match_ids:
        return error(400, "参数 match_ids 不能为空")
    n = _set_selection_status(cup, match_ids, 'rejected')
    try:
        cache.clear()
    except Exception:
        pass
    return success(f"已剔除 {n} 场比赛")


@app.route('/api/admin/players')
def api_admin_players():
    if not _admin_authed():
        return error(403, "无权限访问")
    q = request.args.get('q')
    in_lib = request.args.get('in_library')
    flag = None
    if in_lib in ('1', 'true', 'yes'):
        flag = True
    elif in_lib in ('0', 'false', 'no'):
        flag = False
    players = Player.search_players(q=q, in_library=flag)
    return success({"players": players})


@app.route('/api/admin/player/save')
def api_admin_player_save():
    if not _admin_authed():
        return error(403, "无权限访问")
    player_id = (request.args.get('player_id') or '').strip()
    if not player_id:
        return error(400, "参数 player_id 不能为空")
    try:
        live_url = _parse_optional_http_url(request.args.get('live_url'))
    except ValueError:
        return error(400, "直播间地址必须是有效的 http(s) URL")
    in_library = request.args.get('in_library', '1') not in ('0', 'false', 'no')
    fields = {
        'nickname': request.args.get('nickname') or player_id,
        'alias_name': request.args.get('alias_name') or None,
        'steam_id': request.args.get('steam_id') or None,
        'avatar': request.args.get('avatar') or None,
        'live_url': live_url,
        'in_library': in_library,
    }
    existing = Player.get_or_none(Player.player_id == player_id)
    if existing:
        Player.update(**fields).where(Player.player_id == player_id).execute()
    else:
        Player.create(player_id=player_id, **fields)
    return success("玩家已保存")


@app.route('/api/admin/player/library')
def api_admin_player_library():
    if not _admin_authed():
        return error(403, "无权限访问")
    pids = _parse_ids(request.args.get('player_ids', ''))
    if not pids:
        return error(400, "参数 player_ids 不能为空")
    in_library = request.args.get('in_library', '1') not in ('0', 'false', 'no')
    n = 0
    for pid in pids:
        existing = Player.get_or_none(Player.player_id == pid)
        if existing:
            existing.in_library = in_library
            existing.save()
            n += 1
        elif in_library:
            Player.create(player_id=pid, nickname=pid, in_library=True)
            n += 1
    return success(f"已更新 {n} 名玩家的库内状态")


def _external_token_admin_response(extra=None):
    payload = external_api_token_status()
    payload.update({
        'api_path': '/api/v1/external/players',
        'player_api_path': '/api/v1/external/player',
        'minimum_length': EXTERNAL_TOKEN_MIN_LENGTH,
    })
    if extra:
        payload.update(extra)
    response = success(payload)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response


@app.route('/api/admin/external-api-token', methods=['GET', 'POST'])
def api_admin_external_api_token():
    if request.method == 'GET':
        return _external_token_admin_response()

    data = request.get_json(silent=True) or {}
    raw_action = data.get('action')
    action = raw_action.strip().lower() if isinstance(raw_action, str) else ''
    status = external_api_token_status()
    if action in ('generate', 'save') and status['environment_locked']:
        return error(409, "当前 token 由环境变量管理，请先修改部署配置"), 409

    if action == 'generate':
        token = secrets.token_urlsafe(32)
        save_external_api_token(token)
        return _external_token_admin_response({
            'token': token,
            'message': '新 token 已生成，请立即复制；关闭页面后将无法再查看明文。',
        })
    if action == 'save':
        try:
            save_external_api_token(data.get('token'))
        except ValueError as exc:
            return error(400, str(exc)), 400
        return _external_token_admin_response({'message': 'API token 已保存'})
    if action == 'revoke':
        revoke_database_external_api_token()
        message = ('数据库备用 token 已删除，环境变量 token 仍然有效'
                   if status['environment_locked'] else 'API token 已撤销')
        return _external_token_admin_response({'message': message})
    return error(400, "action 只能是 generate、save 或 revoke"), 400


@app.route('/api/admin/login', methods=['POST'])
def api_admin_login():
    data = request.get_json(silent=True) or {}
    locked, remain = login_locked()
    if locked:
        return error(429, f'尝试过多，请 {remain} 秒后再试'), 429
    if not captcha_ok(data.get('captcha')):
        record_login_fail()
        return error(400, '验证码错误')
    user = verify_password(data.get('username'), data.get('password'))
    if not user:
        record_login_fail()
        locked, remain = login_locked()
        msg = '账号或密码错误' + (f'，已锁定 {remain} 秒' if locked else '')
        return error(401, msg), 401
    clear_login_fail()
    login_admin(user)
    return success({'username': user.username})


@app.route('/api/admin/captcha')
def api_admin_captcha():
    return captcha_response()


@app.route('/api/admin/logout', methods=['POST', 'GET'])
def api_admin_logout():
    logout_admin()
    return success('已退出')


@app.route('/api/admin/me')
def api_admin_me():
    return success({'username': current_admin()})


@app.cli.command("init-db")
def init_db():
    """Initialize the database tables"""
    try:
        create_tables()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")


@app.cli.command("import-history")
def import_history():
    """Import the bundled cs.db history into a fresh PostgreSQL database."""
    result = import_history_sql()
    print(result)


@app.cli.command("reset-admin")
def reset_admin():
    """按环境变量 ADMIN_USERNAME / ADMIN_PASSWORD 重置管理员密码。"""
    from werkzeug.security import generate_password_hash
    username = ADMIN_USERNAME or 'admin'
    password = ADMIN_PASSWORD or 'admin1005'
    user = AdminUser.get_or_none(AdminUser.username == username)
    if user is None:
        AdminUser.create(username=username, password_hash=generate_password_hash(password))
        logger.info(f"已创建管理员 {username}")
    else:
        user.password_hash = generate_password_hash(password)
        user.save()
        logger.info(f"已重置管理员 {username} 的密码")
    print(f"管理员 {username} 已就绪，请用当前 ADMIN_PASSWORD 登录")


def _web_dist():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web', 'dist')


@app.route('/', defaults={'spa_path': ''})
@app.route('/<path:spa_path>')
def spa(spa_path):
    if spa_path.startswith('api/'):
        return error(404, 'not found'), 404
    dist = _web_dist()
    if spa_path:
        candidate = os.path.join(dist, spa_path)
        if os.path.isfile(candidate):
            return send_from_directory(dist, spa_path)
    index = os.path.join(dist, 'index.html')
    if os.path.isfile(index):
        return send_from_directory(dist, 'index.html')
    return error(503, '前端未构建：请在 web/ 目录执行 npm install && npm run build'), 503


if __name__ == '__main__':
    app.run(debug=True, port=5001)
