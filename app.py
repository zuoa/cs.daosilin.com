import os
import secrets
import threading
import time
from datetime import datetime
from urllib.parse import urlsplit

from flask import Flask, g, request, send_file, send_from_directory
from peewee import fn

import title_service
from ajlog import logger
from auth import (captcha_ok, captcha_response, clear_login_fail, current_admin,
                  EXTERNAL_TOKEN_MIN_LENGTH, external_api_token_required,
                  external_api_token_status, login_admin, login_locked, logout_admin,
                  record_login_fail,
                  revoke_database_external_api_token, save_external_api_token,
                  verify_password)
from champion_service import judge_champion
from cache_service import (cached_response, init_cache, invalidate_profiles,
                           invalidate_season, season_scope)
from config import (ADMIN_PASSWORD, ADMIN_USERNAME, DEMO_BACKFILL_DAYS,
                    EXTERNAL_API_TOKEN, LLM_MODEL_NAME, REDIS_URL,
                    SECRET_KEY, SITE_NAME)
from database import (AdminUser, DemoAnalysis, MatchPlayer, Player, PlayerPerfectRankHistory,
                      CupDayChampion,
                      create_tables, Config, PlayerTitle, Match, Season, SeasonRoster,
                      MatchSelection, PlayerSeasonSummary, import_history_sql)
from demo_service import (demo_analysis_enabled, demo_credential_status,
                          load_demo_context,
                          revoke_demo_credential, save_demo_credential,
                          set_demo_analysis_enabled)
from live_service import (LiveRoomError, fetch_live_avatar, normalize_live_room,
                          resolve_live_room)
from scheduler import (crawl_season_with_status, get_crawl_status,
                       crawl_is_running, is_auto_crawl_enabled, season_crawl_phase,
                       set_auto_crawl_enabled, set_crawl_status)
from steam_service import SteamAvatarError, fetch_steam_avatar
from title_service import title_service
from player_summary_service import (admin_row as player_summary_admin_row,
                                    get_public_summary, llm_configured)
from portrait_service import (PortraitError, clamp_transform, configured as portrait_configured,
                              delete_portrait_files, portrait_file_path,
                              portrait_payload, save_portrait)
from utils import success, error

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['EXTERNAL_API_TOKEN'] = EXTERNAL_API_TOKEN

init_cache(app)

try:
    create_tables()
except Exception as e:
    logger.error(f"启动时初始化数据库失败: {e}")


@app.before_request
def start_request_timer():
    if request.path.startswith('/api/'):
        g.request_started_at = time.perf_counter()


@app.after_request
def log_slow_api(response):
    started = getattr(g, 'request_started_at', None)
    if started is None:
        return response
    elapsed_ms = (time.perf_counter() - started) * 1000
    response.headers.setdefault('Server-Timing', f'app;dur={elapsed_ms:.2f}')
    if elapsed_ms >= 500:
        logger.warning(
            f'慢 API method={request.method} path={request.path} '
            f'status={response.status_code} duration_ms={elapsed_ms:.1f} '
            f'cache={response.headers.get("X-Cache", "BYPASS")}'
        )
    return response


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
    match_counts = {
        row.cup_name: int(row.count or 0)
        for row in (Match.select(Match.cup_name, fn.COUNT(Match.id).alias('count'))
                    .where(Match.cup_name.is_null(False))
                    .group_by(Match.cup_name))
    }
    day_counts = {}
    day_rows = (MatchPlayer
                .select(MatchPlayer.cup_name, MatchPlayer.play_day,
                        fn.COUNT(MatchPlayer.id).alias('count'))
                .where(MatchPlayer.cup_name.is_null(False))
                .group_by(MatchPlayer.cup_name, MatchPlayer.play_day)
                .having(fn.COUNT(MatchPlayer.id) > 1))
    for row in day_rows:
        day_counts[row.cup_name] = day_counts.get(row.cup_name, 0) + 1
    for s in seasons:
        Season.annotate(s)
        cup = s.get('cup_name')
        s['match_count'] = match_counts.get(cup, 0)
        s['day_count'] = day_counts.get(cup, 0)
        for key in ('created_at', 'updated_at', 'start_date', 'end_date'):
            val = s.get(key)
            if isinstance(val, datetime):
                s[key] = val.isoformat(timespec='seconds')
    seasons.sort(key=lambda x: (
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
        "avatar": all_players_map.get(player["player_id"], {}).get("avatar") or player["avatar"],
        "player_id": player["player_id"],
        "alias_name": all_players_map.get(player["player_id"], {}).get("alias_name", ""),
        "perfect_score": all_players_map.get(player["player_id"], {}).get("perfect_score"),
        "perfect_level": all_players_map.get(player["player_id"], {}).get("perfect_level"),
        "perfect_stars": all_players_map.get(player["player_id"], {}).get("perfect_stars"),
        "perfect_rank_updated_at": _iso_dt(
            all_players_map.get(player["player_id"], {}).get("perfect_rank_updated_at")
        ),
        "team_name": player.get("team_name", ""),
        "is_champion": player["player_id"] in day_champion.get("champion_team_player_ids", '').split(
            ',') if day_champion else False,
        "is_runner_up": player["player_id"] in day_champion.get("runner_up_team_player_ids", '').split(
            ',') if day_champion else False,
    } for player in players}
    exploits = MatchPlayer.get_match_exploits(cup, players_map.keys(), day)
    stored_titles = (
        PlayerTitle.get_players_titles(players_map.keys(), cup, day)
        if not day else {}
    )

    player_data = []
    for player_id, player in players_map.items():
        d = exploits.get(str(player_id))
        if d:
            player.update(d)
        profile_avatar = all_players_map.get(player_id, {}).get('avatar')
        if profile_avatar:
            player['avatar'] = profile_avatar
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
            player['titles'] = stored_titles.get(str(player['player_id']), [])
    return player_data, MatchPlayer.get_cup_day_set(cup)


def _player_detail_payload(player_id, cup, day=None):
    rec = Player.get_or_none(Player.player_id == player_id)
    if not rec:
        return None, "选手不存在"
    player = rec.to_dict()
    player['portrait'] = portrait_payload(rec)
    for key in ('portrait_original', 'portrait_cutout', 'portrait_scale',
                'portrait_offset_x', 'portrait_offset_y'):
        player.pop(key, None)
    for key in ('created_at', 'updated_at', 'perfect_rank_updated_at'):
        if hasattr(player.get(key), 'isoformat'):
            player[key] = player[key].isoformat()
    player_demo_context = load_demo_context(cup, [player_id])
    player_data = MatchPlayer.get_match_exploits(
        cup, [player_id], day, demo_context=player_demo_context,
    ).get(str(player_id))
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
    historical_map = MatchPlayer.get_match_exploits_by_day(
        cup, [player_id], demo_context=player_demo_context,
    )
    historical_data = []
    for historical_day in cup_days:
        day_data = historical_map.get((str(player_id), historical_day))
        if day_data:
            historical_data.append({'day': historical_day, 'data': day_data})
    all_player_profiles = Player.get_all()
    comparison_stats = MatchPlayer.get_match_exploits(
        cup, [p['player_id'] for p in all_player_profiles], day,
    )
    all_players_data = []
    for p in all_player_profiles:
        p_data = comparison_stats.get(str(p['player_id']))
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
    analysis_by_match = {
        row.match_id: row
        for row in DemoAnalysis.select().where(
            DemoAnalysis.match_id.in_([record['match_id'] for record in match_records])
        )
    } if match_records else {}
    for record in match_records:
        record['start_time'] = _iso_dt(record.get('start_time'))
        record['end_time'] = _iso_dt(record.get('end_time'))
        record['mvp'] = bool(record.get('mvp'))
        analysis = analysis_by_match.get(record['match_id'])
        record['demo_analysis'] = ({
            'status': analysis.status,
            'metric_version': analysis.metric_version,
            'updated_at': _iso_dt(analysis.updated_at),
        } if analysis else {'status': 'pending'})

    return {
        'player': player,
        'perfect_rank_history': [
            {
                'score': sample['score'],
                'level': sample['level'],
                'stars': sample['stars'],
                'sampled_at': _iso_dt(sample['sampled_at']),
            }
            for sample in PlayerPerfectRankHistory.get_player_history(player_id)
        ],
        'player_data': player_data,
        'titles': titles,
        'trophy_history': trophy_history,
        'historical_data': historical_data,
        'player_rankings': player_rankings,
        'map_stats': MatchPlayer.get_player_map_stats(cup, player_id, day),
        'match_records': match_records,
        'kill_matchups': MatchPlayer.get_player_kill_matchups(cup, player_id, day),
        # This report remains season-scoped when the detail page filters a day.
        'season_summary': get_public_summary(cup, player_id),
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
@cached_response(timeout=900, scopes=('seasons',))
def api_seasons():
    return success({
        'seasons': _season_list_payload(),
        'last_crawl_time': Config.get_value("last_crawl_time"),
        'site_name': SITE_NAME,
    })


@app.route('/api/v1/cup/<string:cup>')
@cached_response(timeout=900, scopes=lambda: (season_scope(request.view_args['cup']), 'profiles'))
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
@cached_response(timeout=900, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
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
@cached_response(timeout=900, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
def api_players():
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")

    day = request.args.get('day')

    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))

    all_players = Player.get_all()
    for player in all_players:
        player['portrait'] = portrait_payload(player)
        for key in ('portrait_original', 'portrait_cutout', 'portrait_scale',
                    'portrait_offset_x', 'portrait_offset_y'):
            player.pop(key, None)
    exploits = MatchPlayer.get_match_exploits(
        cup, [player.get('player_id') for player in all_players], day,
    )
    for i in range(len(all_players)):
        player = all_players[i]
        player_id = player.get('player_id')
        profile_avatar = player.get('avatar')
        d = exploits.get(str(player_id))
        if d:
            player.update(d)
        if profile_avatar:
            player['avatar'] = profile_avatar

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
@cached_response(timeout=900, scopes=('external',))
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
@cached_response(timeout=900, scopes=('external',))
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
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError('时间格式应为 ISO 8601 日期时间') from exc


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
    'awp_kill', 'rws', 'damage', 'flash', 'flash_success', 'flash_teammate',
    'throws_count', 'trade_frag_count', 'grenade_damage', 'inferno_damage',
    'vs1', 'vs2', 'vs3', 'vs4', 'vs5', 'win', 'game_count',
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
    avatar_map = {}
    if player_ids:
        for rec in Player.select().where(Player.player_id.in_(player_ids)):
            alias_map[rec.player_id] = rec.alias_name
            avatar_map[rec.player_id] = rec.avatar
    players = []
    for row in player_rows:
        item = {field: getattr(row, field, None) for field in _MATCH_PLAYER_DETAIL_FIELDS}
        item['kast_ratio'] = round(float(row.kast or 0) / row.game_count, 4) if row.game_count else 0.0
        item['in_library'] = row.player_id in library_set
        item['alias_name'] = alias_map.get(row.player_id) or ''
        profile_avatar = avatar_map.get(row.player_id)
        if profile_avatar:
            item['avatar'] = profile_avatar
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


@app.route('/api/v1/match')
@cached_response(timeout=900, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
def api_match_detail():
    """Return details for a match that is already part of a public season."""
    cup = (request.args.get('cup') or '').strip()
    match_id = (request.args.get('match_id') or '').strip()
    if not cup:
        return error(400, "参数 cup 不能为空"), 400
    if not match_id:
        return error(400, "参数 match_id 不能为空"), 400
    payload = _match_detail_payload(cup, match_id)
    if not payload or payload.get('status') != 'approved':
        return error(404, "未找到该比赛"), 404
    return success(payload)


@app.route('/api/admin/season/list')
def api_admin_season_list():
    if not _admin_authed():
        return error(403, "无权限访问")
    seasons = Season.get_all()
    roster_counts = {
        row.season_cup_name: int(row.count or 0)
        for row in (SeasonRoster
                    .select(SeasonRoster.season_cup_name,
                            fn.COUNT(SeasonRoster.id).alias('count'))
                    .group_by(SeasonRoster.season_cup_name))
    }
    selection_counts = {}
    for row in (MatchSelection
                .select(MatchSelection.season_cup_name, MatchSelection.status,
                        fn.COUNT(MatchSelection.id).alias('count'))
                .group_by(MatchSelection.season_cup_name, MatchSelection.status)):
        selection_counts[(row.season_cup_name, row.status)] = int(row.count or 0)
    for s in seasons:
        for key in ('created_at', 'updated_at', 'start_date', 'end_date'):
            val = s.get(key)
            if isinstance(val, datetime):
                s[key] = val.isoformat(timespec='seconds')
        s['roster_count'] = roster_counts.get(s['cup_name'], 0)
        s['approved_count'] = selection_counts.get((s['cup_name'], 'approved'), 0)
        s['rejected_count'] = selection_counts.get((s['cup_name'], 'rejected'), 0)
        s['pending_count'] = s['approved_count']
        if is_auto_crawl_enabled(s['cup_name']) and season_crawl_phase(s) == 'expired':
            set_auto_crawl_enabled(s['cup_name'], False)
            set_crawl_status(s['cup_name'], state='expired', message='赛季已截止，自动采集已停止')
        s['crawl'] = get_crawl_status(s['cup_name'])
    seasons.sort(key=lambda x: (
        x.get('start_date') or '',
        x.get('cup_name') or '',
    ), reverse=True)
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
    invalidate_season(cup, seasons=True)
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
        if not Season.get_by_cup(cup):
            return error(404, "赛季不存在"), 404
        if cup in _crawl_running or crawl_is_running(cup):
            return error(409, "该赛季正在采集，请等待本轮完成后再删除"), 409
        deleted = Season.delete_with_related_data(cup)

    invalidate_season(cup, seasons=True)
    logger.info(f"赛季 {cup} 已删除: {deleted}")
    return success({
        'message': '赛季已删除',
        'cup_name': cup,
        'deleted': deleted,
    })


@app.route('/api/admin/season/roster/get')
@cached_response(timeout=300, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
def api_admin_season_roster_get():
    if not _admin_authed():
        return error(403, "无权限访问")
    cup = request.args.get('cup')
    if not cup:
        return error(400, "参数 cup 不能为空")
    player_ids = SeasonRoster.get_player_ids(cup)
    player_map = {
        player.player_id: player
        for player in Player.select().where(Player.player_id.in_(player_ids))
    } if player_ids else {}
    roster = []
    for pid in player_ids:
        p = player_map.get(pid)
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
    invalidate_season(cup, external=False)
    invalidate_profiles(external=False)
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
@cached_response(timeout=300, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
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
@cached_response(timeout=300, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
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
@cached_response(timeout=300, scopes=lambda: (
    season_scope(request.args.get('cup') or ''), 'profiles'))
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
    invalidate_season(cup, seasons=True)
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
    invalidate_season(cup, seasons=True)
    return success(f"已剔除 {n} 场比赛")


@app.route('/api/admin/players')
@cached_response(timeout=300, scopes=('profiles',))
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
    for player in players:
        player['portrait'] = portrait_payload(player)
        for key in ('portrait_original', 'portrait_cutout', 'portrait_scale',
                    'portrait_offset_x', 'portrait_offset_y'):
            player.pop(key, None)
        live_room_key = Player.live_room_id(player.get('live_url'))
        platform, separator, room_id = live_room_key.partition('_')
        player['live_platform'] = platform if separator else ''
        player['live_room'] = room_id if separator else ''
        player['avatar_source'] = player.get('avatar_source') or 'wanmei'
        if not player.get('wanmei_avatar') and player['avatar_source'] == 'wanmei':
            player['wanmei_avatar'] = player.get('avatar')
    return success({
        "players": players,
        "portrait_service_configured": portrait_configured(),
    })


@app.route('/media/player-portraits/<string:filename>')
def player_portrait_media(filename):
    path = portrait_file_path(filename)
    if path is None or not filename.endswith('-cutout.webp'):
        return error(404, '人物照片不存在'), 404
    response = send_file(path, mimetype='image/webp', conditional=True, max_age=86400)
    response.cache_control.public = True
    response.cache_control.immutable = True
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@app.route('/api/admin/player/<string:player_id>/portrait', methods=['POST', 'PATCH', 'DELETE'])
def api_admin_player_portrait(player_id):
    player = Player.get_or_none(Player.player_id == player_id)
    if player is None:
        return error(404, '玩家不存在'), 404

    if request.method == 'DELETE':
        old_paths = (player.portrait_original, player.portrait_cutout)
        (Player.update(
            portrait_original=None,
            portrait_cutout=None,
            portrait_scale=1.0,
            portrait_offset_x=0.0,
            portrait_offset_y=0.0,
        ).where(Player.player_id == player_id).execute())
        delete_portrait_files(*old_paths)
        invalidate_profiles()
        return success({'message': '人物照片已删除'})

    values = request.form if request.method == 'POST' else (request.get_json(silent=True) or {})
    try:
        scale, offset_x, offset_y = clamp_transform(
            values.get('scale', player.portrait_scale or 1.0),
            values.get('offset_x', player.portrait_offset_x or 0.0),
            values.get('offset_y', player.portrait_offset_y or 0.0),
        )
        if request.method == 'POST':
            old_paths = (player.portrait_original, player.portrait_cutout)
            original, cutout = save_portrait(player_id, request.files.get('portrait'))
            fields = {'portrait_original': original, 'portrait_cutout': cutout}
        else:
            if not player.portrait_cutout:
                return error(400, '请先上传人物照片'), 400
            old_paths = ()
            fields = {}
    except PortraitError as exc:
        return error(400, str(exc)), 400

    fields.update({
        'portrait_scale': scale,
        'portrait_offset_x': offset_x,
        'portrait_offset_y': offset_y,
    })
    Player.update(**fields).where(Player.player_id == player_id).execute()
    if old_paths:
        retained = {fields.get('portrait_original'), fields.get('portrait_cutout')}
        delete_portrait_files(*(path for path in old_paths if path not in retained))
    invalidate_profiles()
    refreshed = Player.get(Player.player_id == player_id)
    return success({
        'message': '人物照片已保存' if request.method == 'POST' else '人物构图已保存',
        'portrait': portrait_payload(refreshed),
    })


@app.route('/api/admin/live-room/resolve')
def api_admin_live_room_resolve():
    if not _admin_authed():
        return error(403, "无权限访问")
    platform = request.args.get('platform')
    room_or_url = request.args.get('room') or request.args.get('live_url')
    include_avatar = request.args.get('include_avatar', '1') not in ('0', 'false', 'no')
    try:
        result = resolve_live_room(platform, room_or_url, include_avatar=include_avatar)
    except LiveRoomError as exc:
        return error(400, str(exc)), 400
    return success(result)


@app.route('/api/admin/steam-avatar/resolve')
def api_admin_steam_avatar_resolve():
    if not _admin_authed():
        return error(403, "无权限访问")
    try:
        result = fetch_steam_avatar(request.args.get('steam_id'))
    except SteamAvatarError as exc:
        return error(400, str(exc)), 400
    return success(result)


def _latest_wanmei_avatar(player_id):
    row = (MatchPlayer.select(MatchPlayer.avatar)
           .where(
               (MatchPlayer.player_id == player_id) &
               MatchPlayer.avatar.is_null(False) &
               (MatchPlayer.avatar != '')
           )
           .order_by(MatchPlayer.updated_at.desc())
           .first())
    return row.avatar if row else None


@app.route('/api/admin/player/save')
def api_admin_player_save():
    if not _admin_authed():
        return error(403, "无权限访问")
    player_id = (request.args.get('player_id') or '').strip()
    if not player_id:
        return error(400, "参数 player_id 不能为空"), 400

    existing = Player.get_or_none(Player.player_id == player_id)
    platform = (request.args.get('live_platform') or '').strip().upper()
    room_input = request.args.get('live_room')
    live_url_input = request.args.get('live_url')
    resolved_room = None
    try:
        if platform or room_input is not None:
            resolved_room = normalize_live_room(platform, room_input or live_url_input)
            live_url = resolved_room.get('live_url') or None
        else:
            # Keep the old API contract for clients that only submit live_url.
            live_url = _parse_optional_http_url(live_url_input)
    except (ValueError, LiveRoomError) as exc:
        message = str(exc) or "直播间地址必须是有效的 http(s) URL"
        return error(400, message), 400

    requested_source = (request.args.get('avatar_source') or '').strip().lower()
    if requested_source and requested_source not in ('wanmei', 'steam', 'live'):
        return error(400, "头像来源只能是 wanmei、steam 或 live"), 400

    legacy_avatar = (request.args.get('avatar') or '').strip() or None
    current_source = (existing.avatar_source or 'wanmei') if existing else 'wanmei'
    wanmei_avatar = (
        (existing.wanmei_avatar if existing else None) or
        legacy_avatar or
        _latest_wanmei_avatar(player_id) or
        (existing.avatar if existing and current_source == 'wanmei' else None)
    )
    steam_avatar = existing.steam_avatar if existing else None
    live_avatar = existing.live_avatar if existing else None
    avatar_source = requested_source or current_source
    steam_id = (request.args.get('steam_id') or '').strip() or None

    if requested_source == 'steam':
        try:
            steam_profile = fetch_steam_avatar(
                steam_id or (existing.steam_id if existing else None) or player_id
            )
        except SteamAvatarError as exc:
            return error(400, str(exc)), 400
        steam_id = steam_profile['steam_id']
        steam_avatar = steam_profile['avatar']

    if requested_source == 'live':
        if not resolved_room or not live_url:
            return error(400, "选择直播间头像前，请填写直播平台和房间号"), 400
        try:
            live_avatar = fetch_live_avatar(
                resolved_room.get('platform'), resolved_room.get('room_id')
            )
        except LiveRoomError as exc:
            return error(400, str(exc)), 400

    avatars = {
        'wanmei': wanmei_avatar,
        'steam': steam_avatar,
        'live': live_avatar,
    }
    selected_avatar = avatars.get(avatar_source)
    if not requested_source and legacy_avatar:
        # Old callers explicitly edited the single avatar field.
        wanmei_avatar = legacy_avatar
        selected_avatar = legacy_avatar
        avatar_source = 'wanmei'

    in_library = request.args.get('in_library', '1') not in ('0', 'false', 'no')
    fields = {
        'nickname': request.args.get('nickname') or player_id,
        'alias_name': request.args.get('alias_name') or None,
        'steam_id': steam_id,
        'avatar': selected_avatar,
        'avatar_source': avatar_source,
        'wanmei_avatar': wanmei_avatar,
        'steam_avatar': steam_avatar,
        'live_avatar': live_avatar,
        'live_url': live_url,
        'in_library': in_library,
    }
    if existing:
        Player.update(**fields).where(Player.player_id == player_id).execute()
    else:
        Player.create(player_id=player_id, **fields)
    invalidate_profiles()
    return success({
        'message': '玩家已保存',
        'avatar': selected_avatar,
        'avatar_source': avatar_source,
        'live_url': live_url,
    })


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
    invalidate_profiles()
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


def _demo_admin_status(extra=None):
    payload = demo_credential_status()
    counts = {
        row.status: row.count
        for row in (DemoAnalysis
                    .select(DemoAnalysis.status, fn.COUNT(DemoAnalysis.id).alias('count'))
                    .group_by(DemoAnalysis.status))
    }
    payload.update({
        'enabled': demo_analysis_enabled(),
        'backfill_days': DEMO_BACKFILL_DAYS,
        'job_counts': counts,
    })
    if extra:
        payload.update(extra)
    response = success(payload)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    return response


@app.route('/api/admin/demo-settings', methods=['GET', 'POST'])
def api_admin_demo_settings():
    if request.method == 'GET':
        return _demo_admin_status()
    data = request.get_json(silent=True) or {}
    action = str(data.get('action') or 'save').strip().lower()
    if action == 'enable':
        set_demo_analysis_enabled(True)
        try:
            from demo_tasks import reconcile_demo_jobs
            result = reconcile_demo_jobs()
        except Exception as exc:
            logger.error(f'Demo 分析开启后入队失败: {exc}')
            result = {'scheduled': 0}
        return _demo_admin_status({'message': f'Demo 分析已开启，已调度 {result.get("scheduled", 0)} 场'})
    if action == 'disable':
        set_demo_analysis_enabled(False)
        return _demo_admin_status({'message': 'Demo 分析已关闭；平台数据采集继续运行'})
    if action == 'save':
        try:
            save_demo_credential(data.get('steam_id'), data.get('access_token'))
        except ValueError as exc:
            return error(400, str(exc)), 400
        try:
            from demo_tasks import reconcile_demo_jobs
            result = reconcile_demo_jobs()
        except Exception as exc:
            logger.error(f'Demo 凭证保存后入队失败: {exc}')
            result = {'scheduled': 0}
        return _demo_admin_status({'message': f'Demo 凭证已加密保存，已调度 {result.get("scheduled", 0)} 场'})
    if action == 'revoke':
        revoke_demo_credential()
        return _demo_admin_status({'message': 'Demo 覆盖凭证已删除，已恢复使用默认 WMPVP 采集凭证'})
    if action == 'backfill':
        from demo_tasks import reconcile_demo_jobs
        result = reconcile_demo_jobs()
        return _demo_admin_status({'message': f'已扫描 {result["eligible"]} 场，调度 {result["scheduled"]} 场'})
    return error(400, 'action 只能是 enable、disable、save、revoke 或 backfill'), 400


@app.route('/api/admin/demo-jobs')
def api_admin_demo_jobs():
    status = (request.args.get('status') or '').strip()
    try:
        limit = min(max(int(request.args.get('limit') or 50), 1), 200)
    except ValueError:
        return error(400, 'limit 必须是整数'), 400
    query = DemoAnalysis.select().order_by(DemoAnalysis.updated_at.desc())
    if status:
        query = query.where(DemoAnalysis.status == status)
    jobs = []
    for row in query.limit(limit):
        item = row.to_dict()
        for key, value in list(item.items()):
            if isinstance(value, datetime):
                item[key] = value.isoformat(timespec='seconds')
        # Filesystem locations are operational details, not admin API data.
        item.pop('archive_path', None)
        item.pop('raw_result_path', None)
        jobs.append(item)
    return success({'jobs': jobs, 'count': len(jobs)})


@app.route('/api/admin/demo-jobs/<path:match_id>/retry', methods=['POST'])
def api_admin_demo_job_retry(match_id):
    if not Match.select().where(Match.match_id == match_id).exists():
        return error(404, '比赛不存在'), 404
    try:
        from demo_tasks import schedule_demo_analysis
        row = schedule_demo_analysis(match_id, force=True)
    except Exception as exc:
        return error(503, f'任务入队失败：{exc}'), 503
    return success({'match_id': match_id, 'status': row.status})


@app.route('/api/admin/player-summaries')
def api_admin_player_summaries():
    cup = (request.args.get('cup') or '').strip()
    status = (request.args.get('status') or '').strip()
    try:
        page = max(1, int(request.args.get('page') or 1))
        page_size = min(100, max(1, int(request.args.get('page_size') or 30)))
    except (TypeError, ValueError):
        return error(400, 'page 和 page_size 必须是整数'), 400
    query = PlayerSeasonSummary.select()
    if cup:
        query = query.where(PlayerSeasonSummary.cup_name == cup)
    if status:
        query = query.where(PlayerSeasonSummary.status == status)
    total = query.count()
    rows = list(query.order_by(PlayerSeasonSummary.updated_at.desc())
                .paginate(page, page_size))
    count_query = (PlayerSeasonSummary
                   .select(PlayerSeasonSummary.status,
                           fn.COUNT(PlayerSeasonSummary.id).alias('count'))
                   .group_by(PlayerSeasonSummary.status))
    if cup:
        count_query = count_query.where(PlayerSeasonSummary.cup_name == cup)
    counts = {row.status: row.count for row in count_query}
    return success({
        'configured': llm_configured(),
        'redis_configured': bool(REDIS_URL),
        'model': LLM_MODEL_NAME,
        'counts': counts,
        'items': [player_summary_admin_row(row) for row in rows],
        'total': total,
        'page': page,
        'page_size': page_size,
    })


@app.route('/api/admin/player-summaries/rebuild', methods=['POST'])
def api_admin_player_summaries_rebuild():
    if not llm_configured():
        return error(409, '服务端尚未配置 LLM_API_KEY'), 409
    if not REDIS_URL:
        return error(409, '服务端尚未配置 REDIS_URL'), 409
    data = request.get_json(silent=True) or {}
    cup = str(data.get('cup') or '').strip()
    player_id = str(data.get('player_id') or '').strip()
    if not cup:
        return error(400, '参数 cup 不能为空'), 400
    if not Season.get_by_cup(cup):
        return error(404, '赛季不存在'), 404
    from player_summary_tasks import (reconcile_player_summaries,
                                      schedule_player_summary)
    try:
        if player_id:
            row, queued = schedule_player_summary(cup, player_id, force=True)
            if row is None:
                return error(404, '该选手在此赛季无数据'), 404
            result = {'eligible': 1, 'scheduled': int(queued),
                      'skipped': int(not queued)}
        else:
            result = reconcile_player_summaries(cup_name=cup, force=True)
    except Exception as exc:
        logger.error(f'AI 点评重算入队失败 cup={cup} player={player_id}: {exc}')
        return error(503, 'AI 点评队列暂时不可用'), 503
    return success({
        **result,
        'message': f'已重新调度 {result.get("scheduled", 0)} 位选手的赛季点评',
    })


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
