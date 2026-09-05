# 配置日志
import datetime
import json
import time
import unicodedata

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from ajlog import logger
from champion_service import judge_champion
from config import (PERFECT_RANK_REFRESH_HOURS, PERFECT_RANK_REQUEST_INTERVAL,
                    WMPVP_ACCESS_TOKEN, WMPVP_STEAM_ID)

from database import (create_tables, Match, MatchPlayer, Player, PlayerPerfectRankHistory,
                      Config, Season, SeasonRoster, MatchSelection)
from demo_service import load_demo_credential
from perfect_service import (clear_perfect_rank_cache, get_perfect_rank,
                             resolve_steam_id64)
from cache_service import invalidate_profiles, invalidate_season
from title_service import title_service
from utils import get_play_day
from wm import WMAPI


CRAWL_HEARTBEAT_TIMEOUT = datetime.timedelta(minutes=3)


def canonical_match_id(match_id):
    """Return the stable database identity used for a WMPVP match.

    WMPVP may return the same PVP match as either ``123`` or ``PVP@123``
    depending on the endpoint.  Persisting those values verbatim creates two
    database matches for one game, so numeric IDs are always stored with the
    PVP prefix.
    """
    value = str(match_id or '').strip()
    if not value:
        return ''
    prefix, separator, suffix = value.partition('@')
    if separator and prefix.upper() == 'PVP' and suffix.isdigit():
        return f'PVP@{suffix}'
    if value.isdigit():
        return f'PVP@{value}'
    return value


def _normalize_cup_label(value):
    """Normalize a displayed/API cup name for stable matching."""
    return ''.join(unicodedata.normalize('NFKC', str(value or '')).split()).casefold()


def _official_cup_matches(season, api_cup):
    """Match an official WMPVP cup against the season's display name."""
    display_name = (
        season.get('cup_alias')
        or season.get('name')
        or season.get('cup_name')
        or ''
    )
    return bool(
        _normalize_cup_label(api_cup)
        and _normalize_cup_label(api_cup) == _normalize_cup_label(display_name)
    )


def _store_match(match_data, assigned_cup_name=None, play_day=None, match_id=None):
    """把一场比赛详情入库（Match + MatchPlayer + Player）。

    assigned_cup_name：传赛季的内部 cup_name（URL 标识）。
    play_day：已算好的比赛日（自定义候选路径传入）；未传则按 -3h 比赛日计算。
    """
    match_base_info = match_data.get('base', {})
    detail_match_id = canonical_match_id(match_base_info.get('matchId'))
    match_id = canonical_match_id(match_id or detail_match_id)
    if not match_id:
        raise ValueError('比赛详情缺少 matchId')
    if detail_match_id and detail_match_id != match_id:
        logger.warning(
            f'比赛列表 ID {match_id} 与详情 ID {detail_match_id} 不一致，按列表 ID 入库'
        )
    match_model = {
        "match_id": match_id,
        "map_name": match_base_info.get('map'),
        "map_name_en": match_base_info.get('mapEn'),
        "map_url": match_base_info.get('mapUrl'),
        "map_logo": match_base_info.get('mapLogo'),
        "start_time": match_base_info.get('startTime'),
        "end_time": match_base_info.get('endTime'),
        "duration": match_base_info.get('duration'),
        "win_team": match_base_info.get('winTeam'),
        "team1_id": match_base_info.get('team1PvpId'),
        "team1_name": match_base_info.get('team1Name'),
        "team1_logo": match_base_info.get('team1Logo'),
        "team2_id": match_base_info.get('team2PvpId'),
        "team1_score": match_base_info.get('score1'),
        "team2_name": match_base_info.get('team2Name'),
        "team2_logo": match_base_info.get('team2Logo'),
        "team2_score": match_base_info.get('score2'),
        "team1_half_score": match_base_info.get('halfScore1'),
        "team2_half_score": match_base_info.get('halfScore2'),
        "team1_extra_score": match_base_info.get('extraScore1'),
        "team2_extra_score": match_base_info.get('extraScore2'),
        "cup_name": assigned_cup_name,
        "cup_logo": match_base_info.get('cupLogo'),
        "game_mode": match_base_info.get('mode'),
        "notes": json.dumps(match_data, default=str, ensure_ascii=False)
    }
    # 沿用 -3 小时比赛日（官方、自定义一致）
    match_model['play_day'] = play_day or get_play_day(match_model.get('end_time'), 3)

    existing = Match.get_by_match_id(match_id)
    if not existing:
        Match.create(**match_model)
        logger.info(f"比赛 {match_id} 已保存")
    else:
        match_updates = dict(match_model)
        if not assigned_cup_name:
            match_updates.pop('cup_name', None)
        Match.update(**match_updates).where(Match.match_id == match_id).execute()
        if assigned_cup_name and existing.get('cup_name') != assigned_cup_name:
            MatchPlayer.update(cup_name=assigned_cup_name).where(MatchPlayer.match_id == match_id).execute()

    players = match_data.get('players', [])
    for match_player in players:
        player_id = match_player.get('playerId')

        # MatchPlayer Model
        match_player_model = {
            "match_id": match_id,
            "player_id": player_id,
            "nickname": match_player.get('nickName'),
            "avatar": match_player.get('avatar'),
            "team": match_player.get('team'),
            "kill": match_player.get('kill'),
            "bot_kill": match_player.get('botKill'),
            "neg_kill": match_player.get('negKill'),
            "handgun_kill": match_player.get('handGunKill'),
            "entry_kill": match_player.get('entryKill'),
            "awp_kill": match_player.get('awpKill'),
            "death": match_player.get('death'),
            "entry_death": match_player.get('entryDeath'),
            "assist": match_player.get('assist'),
            "headshot": match_player.get('headShot'),
            "headshot_ratio": match_player.get('headShotRatio'),
            "rating": match_player.get('rating'),
            "pw_rating": match_player.get('pwRating'),
            "damage": match_player.get('damage'),
            "item_throw": match_player.get('itemThrow'),
            "flash": match_player.get('flash'),
            "flash_teammate": match_player.get('flashTeammate'),
            "flash_success": match_player.get('flashSuccess'),
            "end_game": match_player.get('endGame'),
            "mvp_value": match_player.get('mvpValue'),
            "score": match_player.get('score'),
            "ban_type": match_player.get('banType'),
            "two_kill": match_player.get('twoKill'),
            "three_kill": match_player.get('threeKill'),
            "four_kill": match_player.get('fourKill'),
            "five_kill": match_player.get('fiveKill'),
            "multi_kills": match_player.get('multiKills'),
            "vs1": match_player.get('vs1'),
            "vs2": match_player.get('vs2'),
            "vs3": match_player.get('vs3'),
            "vs4": match_player.get('vs4'),
            "vs5": match_player.get('vs5'),
            "headshot_count": match_player.get('headShotCount'),
            "dmg_armor": match_player.get('dmgArmor'),
            "dmg_health": match_player.get('dmgHealth'),
            "adpr": match_player.get('adpr'),
            "fire_count": match_player.get('fireCount'),
            "hit_count": match_player.get('hitCount'),
            "rws": match_player.get('rws'),
            "kast": match_player.get('kast'),
            "rank": match_player.get('rank'),
            "old_rank": match_player.get('oldRank'),
            "we": match_player.get('we'),
            "throws_count": match_player.get('throwsCnt'),
            "team_id": match_player.get('teamId'),
            "team_name": match_model.get(f"team1_name") if match_player.get('team') == 1 else match_model.get("team2_name"),
            "snipe_num": match_player.get('snipeNum'),
            "first_death": match_player.get('firstDeath'),
            "mvp": match_player.get('mvp'),
            'cup_name': match_model.get('cup_name'),
            'win': 1 if match_model.get("win_team") == match_player.get('team') else 0,
            'game_count': match_model.get('team1_score') + match_model.get('team2_score'),
            'trade_frag_count': match_player.get('tradeFragCount') or 0,
            'grenade_damage': match_player.get('grenadeDamage') or 0,
            'inferno_damage': match_player.get('infernoDamage') or 0,
            'kill_map': json.dumps(match_player.get('killMap') or {}, ensure_ascii=False),
        }

        if match_model.get("play_day") is not None:
            match_player_model['play_day'] = match_model.get("play_day")

        if not MatchPlayer.is_exist(match_id, player_id):
            MatchPlayer.create(**match_player_model)
        else:
            player_updates = dict(match_player_model)
            if not assigned_cup_name:
                player_updates.pop('cup_name', None)
            (MatchPlayer.update(**player_updates)
             .where(MatchPlayer.match_id == match_id, MatchPlayer.player_id == player_id)
             .execute())

        player_model = {
            "player_id": player_id,
            "nickname": match_player.get('nickName'),
            "avatar": match_player.get('avatar'),
            "wanmei_avatar": match_player.get('avatar'),
            "avatar_source": "wanmei",
        }

        if not Player.is_exist(player_id):
            player_model['in_library'] = False
            Player.create(**player_model)
            logger.info(f"玩家 {player_id} 已保存（非库内）")

    try:
        from demo_service import demo_analysis_enabled
        if demo_analysis_enabled():
            from demo_tasks import schedule_demo_analysis
            schedule_demo_analysis(match_id)
    except Exception as exc:
        # Demo is a second-stage enrichment and must never block the crawl.
        logger.error(f'Demo 任务入队失败 match={match_id}: {exc}')
    return match_id


def _as_datetime(value):
    if isinstance(value, datetime.datetime):
        return value
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
    except (TypeError, ValueError):
        return None


def _in_season_window(season, match_end_time):
    """判断比赛结束时间是否落在赛季闭区间内，精确到秒。"""
    match_time = _as_datetime(match_end_time)
    if not match_time:
        return False
    start = _as_datetime(season.get('start_date'))
    end = _as_datetime(season.get('end_date'))
    if start and match_time < start:
        return False
    if end and match_time > end:
        return False
    return True


def _new_wm():
    return WMAPI(token=WMPVP_ACCESS_TOKEN, token_steam_id=WMPVP_STEAM_ID)


def _library_hit(player_ids, library_ids):
    if not player_ids:
        return 0, 0.0
    hit = len(set(player_ids) & library_ids)
    return hit, hit / len(player_ids)


def crawl_data(default_player_id='76561198068647788'):
    """兼容：爬单个玩家近期官方比赛，仅入库 active official 赛季。"""
    wm = _new_wm()
    match_list = wm.get_match_list(default_player_id, 10)
    official_seasons = Season.get_active_by_type('official')
    if not official_seasons:
        return

    for match in match_list:
        source_match_id = match.get('matchId')
        match_id = canonical_match_id(source_match_id)
        api_cup = match.get('cupName')
        season = next(
            (item for item in official_seasons if _official_cup_matches(item, api_cup)),
            None,
        )
        if not match_id or not season:
            continue
        match_data = wm.get_match(source_match_id)
        if match_data:
            _store_match(
                match_data,
                assigned_cup_name=season['cup_name'],
                match_id=match_id,
            )


def get_crawl_status(cup_name):
    raw = Config.get_value(f'crawl_status:{cup_name}')
    if not raw:
        status = {'state': 'idle'}
    else:
        try:
            status = json.loads(raw)
        except Exception:
            status = {'state': 'idle', 'message': raw}
    status['auto_enabled'] = is_auto_crawl_enabled(cup_name)
    return status


def is_auto_crawl_enabled(cup_name):
    return Config.get_value(f'crawl_enabled:{cup_name}') == '1'


def set_auto_crawl_enabled(cup_name, enabled):
    Config.set_value(f'crawl_enabled:{cup_name}', '1' if enabled else '0')


def _stored_crawl_status(cup_name):
    raw = Config.get_value(f'crawl_status:{cup_name}')
    if not raw:
        return {'state': 'idle'}
    try:
        return json.loads(raw)
    except Exception:
        return {'state': 'idle', 'message': raw}


def set_crawl_status(cup_name, **fields):
    current = _stored_crawl_status(cup_name)
    current.update(fields)
    Config.set_value(f'crawl_status:{cup_name}', json.dumps(current, ensure_ascii=False))


def _crawl_status_time(value):
    return _as_datetime(value)


def crawl_is_running(cup_name, now=None):
    """只把心跳仍然新鲜的 running 视为运行中，并自动恢复崩溃遗留状态。"""
    status = _stored_crawl_status(cup_name)
    if status.get('state') != 'running':
        return False
    now = now or datetime.datetime.now()
    heartbeat = _crawl_status_time(status.get('heartbeat_at') or status.get('started_at'))
    if heartbeat and now - heartbeat <= CRAWL_HEARTBEAT_TIMEOUT:
        return True
    set_crawl_status(
        cup_name,
        state='interrupted',
        message='上一轮采集进程已中断，已自动解除锁定，可重新采集',
        finished_at=now.strftime("%Y-%m-%d %H:%M:%S"),
    )
    logger.warning(f'赛季 {cup_name} 采集心跳已过期，解除 running 状态')
    return False


def touch_crawl_heartbeat(cup_name):
    set_crawl_status(cup_name, heartbeat_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def season_crawl_phase(season, now=None):
    """返回赛季在当前时间所处的采集阶段。"""
    now = now or datetime.datetime.now()
    start = _as_datetime(season.get('start_date'))
    end = _as_datetime(season.get('end_date'))
    if end and now > end:
        return 'expired'
    if start and now < start:
        return 'waiting'
    return 'active'


def expire_auto_crawl(season):
    """赛季截止后永久关闭该赛季的自动采集。"""
    cup_name = season.get('cup_name')
    set_auto_crawl_enabled(cup_name, False)
    set_crawl_status(
        cup_name,
        state='expired',
        message='赛季已截止，自动采集已停止',
        finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def _schedule_player_summaries(cup_name):
    """Best-effort enrichment; an LLM outage must never fail season crawling."""
    try:
        from player_summary_tasks import reconcile_player_summaries
        result = reconcile_player_summaries(cup_name=cup_name)
        logger.info(
            f'AI 点评对账完成 cup={cup_name} eligible={result.get("eligible", 0)} '
            f'scheduled={result.get("scheduled", 0)}'
        )
        return result
    except Exception as exc:
        logger.error(f'AI 点评调度失败 cup={cup_name}: {exc}')
        return {'eligible': 0, 'scheduled': 0, 'error': str(exc)}


def crawl_season_with_status(cup_name, manual=False):
    """采集一个赛季；manual=True 时允许对已截止/未开始赛季按既定时间窗补采。"""
    season = Season.get_by_cup(cup_name)
    if not season:
        raise ValueError(f'赛季不存在: {cup_name}')
    phase = season_crawl_phase(season)
    if phase == 'expired' and not manual:
        expire_auto_crawl(season)
        return {'cup_name': cup_name, 'visited': 0, 'included': 0, 'skipped': 0, 'expired': True}
    if phase == 'waiting' and not manual:
        set_crawl_status(
            cup_name,
            state='scheduled',
            message=f"自动采集已启动，将在 {season.get('start_date')} 后开始获取",
        )
        return {'cup_name': cup_name, 'visited': 0, 'included': 0, 'skipped': 0, 'waiting': True}
    set_crawl_status(
        cup_name,
        state='running',
        message='采集中',
        started_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        heartbeat_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        finished_at=None,
        stats=None,
    )
    try:
        stats = crawl_season(season, ignore_deadline=manual)
        if season_crawl_phase(season) == 'expired' and not manual:
            set_auto_crawl_enabled(cup_name, False)
            set_crawl_status(
                cup_name,
                state='expired',
                message='赛季已截止，本轮采集已结束，自动采集已停止',
                finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                stats=stats,
            )
            Config.set_value("last_crawl_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            invalidate_season(cup_name, seasons=True)
            _schedule_player_summaries(cup_name)
            return stats
        keep_scheduled = is_auto_crawl_enabled(cup_name) and not manual
        set_crawl_status(
            cup_name,
            state='scheduled' if keep_scheduled else 'done',
            message=(
                f"本轮完成：访问 {stats.get('visited')} 人，纳入 {stats.get('included')} 场，"
                f"跳过 {stats.get('skipped')} 场；每 10 分钟自动获取"
                if keep_scheduled
                else f"完成：访问 {stats.get('visited')} 人，纳入 {stats.get('included')} 场，跳过 {stats.get('skipped')} 场"
            ),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            stats=stats,
        )
        Config.set_value("last_crawl_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        invalidate_season(cup_name, seasons=True)
        _schedule_player_summaries(cup_name)
        return stats
    except Exception as e:
        set_crawl_status(
            cup_name,
            state='error',
            message=str(e),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        raise


def crawl_season(season, ignore_deadline=False):
    """按赛季采集：种子滚雪球 + 时间窗 + 库内占比门槛，默认写入 cup_name。"""
    cup_name = season.get('cup_name')
    match_type = season.get('match_type') or 'custom'
    hit_ratio = season.get('hit_ratio')
    if hit_ratio is None:
        hit_ratio = 0.6
    try:
        hit_ratio = float(hit_ratio)
    except (TypeError, ValueError):
        hit_ratio = 0.6

    canonical_seeds = SeasonRoster.get_player_ids(cup_name)
    seeds = list(dict.fromkeys(
        account_id
        for player_id in canonical_seeds
        for account_id in Player.account_ids(player_id)
    ))
    if not seeds:
        logger.info(f"赛季 {cup_name} 种子为空，跳过爬取")
        return {'cup_name': cup_name, 'visited': 0, 'included': 0, 'skipped': 0}

    library_ids = set(Player.get_library_ids())
    wm = _new_wm()
    queue = list(seeds)
    visited = set()
    seen_matches = set()
    included = 0
    skipped = 0

    logger.info(
        f"====== 开始采集赛季 {cup_name} type={match_type} "
        f"window={season.get('start_date')}~{season.get('end_date')} "
        f"hit_ratio={hit_ratio} seeds={len(seeds)} library={len(library_ids)} ======"
    )

    while queue:
        touch_crawl_heartbeat(cup_name)
        if not ignore_deadline and season_crawl_phase(season) == 'expired':
            logger.info(f"赛季 {cup_name} 已到截止时间，结束本轮采集")
            break
        pid = queue.pop(0)
        if pid in visited:
            continue
        visited.add(pid)
        try:
            start_time = _as_datetime(season.get('start_date'))
            older_than_day = start_time.strftime('%Y%m%d') if start_time else None
            match_list = wm.get_match_list(pid, 100, older_than_day=older_than_day)
        except Exception as e:
            logger.error(f"拉取玩家 {pid} 比赛列表失败: {e}")
            time.sleep(10)
            continue

        for match in match_list:
            touch_crawl_heartbeat(cup_name)
            if not ignore_deadline and season_crawl_phase(season) == 'expired':
                queue.clear()
                logger.info(f"赛季 {cup_name} 已到截止时间，停止继续获取比赛")
                break
            source_match_id = match.get('matchId')
            match_id = canonical_match_id(source_match_id)
            if not match_id or match_id in seen_matches:
                continue
            seen_matches.add(match_id)

            play_day = get_play_day(match.get('endTime'), 3)
            if not _in_season_window(season, match.get('endTime')):
                continue

            api_cup = match.get('cupName') or ''
            if match_type == 'official':
                if not _official_cup_matches(season, api_cup):
                    continue
            else:
                if api_cup:
                    continue

            match_data = wm.get_match(source_match_id)
            if not match_data:
                continue

            player_ids = [p.get('playerId') for p in match_data.get('players', []) if p.get('playerId')]
            hit_count, ratio = _library_hit(player_ids, library_ids)
            if match_type != 'official' and ratio < hit_ratio:
                skipped += 1
                logger.debug(
                    f"比赛 {match_id} 库内占比 {hit_count}/{len(player_ids)}={ratio:.2f} < {hit_ratio}，跳过"
                )
                continue

            assigned = MatchSelection.upsert_included(
                match_id, cup_name, play_day, hit_count, source_type=match_type
            )
            if assigned:
                _store_match(
                    match_data,
                    assigned_cup_name=cup_name,
                    play_day=play_day,
                    match_id=match_id,
                )
                included += 1
                logger.info(
                    f"比赛 {match_id} 纳入 {cup_name}（库内 {hit_count}/{len(player_ids)}）"
                )
                for other in player_ids:
                    if other not in visited:
                        queue.append(other)
            else:
                skipped += 1
                logger.debug(f"比赛 {match_id} 已剔除，不写回 {cup_name}")

        time.sleep(10)

    stats = {'cup_name': cup_name, 'visited': len(visited), 'included': included, 'skipped': skipped}
    logger.info(f"====== 赛季 {cup_name} 采集完成 {stats} ======")
    return stats


def crawl_all():
    today = (datetime.datetime.now() - datetime.timedelta(hours=3)).strftime("%Y%m%d")
    seasons = Season.get_active()
    enabled_count = sum(1 for season in seasons if is_auto_crawl_enabled(season.get('cup_name')))
    crawled = False

    logger.info(f"====== 检查自动采集赛季 {enabled_count} 个，今日 {today} ======")
    for season in seasons:
        cup_name = season.get('cup_name')
        if not is_auto_crawl_enabled(cup_name):
            continue
        phase = season_crawl_phase(season)
        if phase == 'expired':
            expire_auto_crawl(season)
            logger.info(f"赛季 {cup_name} 已截止，自动采集已停止")
            continue
        if phase == 'waiting':
            set_crawl_status(
                cup_name,
                state='scheduled',
                message=f"自动采集已启动，将在 {season.get('start_date')} 后开始获取",
            )
            continue
        if crawl_is_running(cup_name):
            logger.info(f"赛季 {cup_name} 上一轮仍在采集，本轮跳过")
            continue
        try:
            crawl_season_with_status(cup_name)
            crawled = True
        except Exception as e:
            logger.error(f"采集赛季 {cup_name} 失败: {e}")

    logger.info(f"====== 采集完成 ======")
    if crawled:
        calc_titles(today)


def refresh_perfect_ranks():
    """Refresh and persist Perfect World ranks for every known player."""
    players = [
        player for player in
        Player.select().order_by(Player.in_library.desc(), Player.player_id.asc())
        if not getattr(player, 'parent_player_id', None)
    ]
    clear_perfect_rank_cache()
    try:
        rank_credential = load_demo_credential()
    except ValueError as exc:
        logger.warning(f'完美段位星数凭证不可用，本次仅刷新基础段位: {exc}')
        rank_credential = None
    stats = {'total': len(players), 'updated': 0, 'failed': 0, 'invalid': 0}
    started_at = datetime.datetime.now()
    logger.info(f"====== 开始刷新完美段位，共 {len(players)} 名玩家 ======")

    for index, player in enumerate(players):
        steam_id = resolve_steam_id64(player.steam_id, player.player_id)
        if not steam_id:
            stats['invalid'] += 1
            continue

        rank = get_perfect_rank(steam_id, credential=rank_credential)
        if rank is None:
            stats['failed'] += 1
        else:
            refreshed_at = datetime.datetime.now()
            with Player._meta.database.atomic():
                (Player.update(
                    perfect_score=rank['score'],
                    perfect_level=rank['level'],
                    perfect_stars=rank.get('stars'),
                    perfect_rank_updated_at=refreshed_at,
                ).where(Player.player_id == player.player_id).execute())
                PlayerPerfectRankHistory.create(
                    player_id=player.player_id,
                    score=rank['score'],
                    level=rank['level'],
                    stars=rank.get('stars'),
                    sampled_at=refreshed_at,
                )
            stats['updated'] += 1

        if index < len(players) - 1 and PERFECT_RANK_REQUEST_INTERVAL > 0:
            time.sleep(PERFECT_RANK_REQUEST_INTERVAL)

    finished_at = datetime.datetime.now()
    Config.set_value('perfect_rank_last_refresh', finished_at.strftime('%Y-%m-%d %H:%M:%S'))
    Config.set_value('perfect_rank_refresh_stats', json.dumps(stats, ensure_ascii=False))
    invalidate_profiles()
    elapsed = (finished_at - started_at).total_seconds()
    logger.info(f"====== 完美段位刷新完成 {stats}，耗时 {elapsed:.1f}s ======")
    return stats



def create_scheduler():
    executors = {
        'default': ThreadPoolExecutor(max_workers=5)  # 根据需要调整数量
    }

    scheduler = BlockingScheduler(executors=executors)

    # 启用自动采集的赛季每 10 分钟获取一次；赛季截止后会在 crawl_all 中自动停用。
    scheduler.add_job(
        func=crawl_all,
        trigger=CronTrigger(minute='*/10'),
        id='crawl_job',
        name='赛季自动采集任务',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
    )
    logger.info("调度器已创建，任务已添加")

    scheduler.add_job(
        func=judge_all_champions,
        trigger=CronTrigger(hour='0-2', minute='*/5'),
        id='job_judge_champion',
        name='冠军判断任务',
        replace_existing=True
    )

    scheduler.add_job(
        func=refresh_perfect_ranks,
        trigger=CronTrigger(hour=PERFECT_RANK_REFRESH_HOURS, minute='15'),
        id='refresh_perfect_ranks',
        name='完美段位定时刷新任务',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=10),
    )
    logger.info(
        f'完美段位任务已添加：每天 {PERFECT_RANK_REFRESH_HOURS} 点的 15 分执行，启动后立即执行一次'
    )

    from demo_tasks import cleanup_demo_archives, reconcile_demo_jobs
    scheduler.add_job(
        func=reconcile_demo_jobs,
        trigger=CronTrigger(minute='*/5'),
        id='demo_analysis_reconcile',
        name='Demo 分析任务对账与近 30 天回填',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=30),
    )
    logger.info('Demo 分析对账任务已添加：后台开启后每 5 分钟执行并回填近 30 天')

    scheduler.add_job(
        func=cleanup_demo_archives,
        trigger=CronTrigger(minute='17'),
        id='demo_archive_cleanup',
        name='Demo 归档保留期清理',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=60),
    )
    logger.info('Demo 归档清理任务已添加：每小时删除超过保留期的文件')

    from player_summary_tasks import reconcile_player_summaries
    scheduler.add_job(
        func=reconcile_player_summaries,
        trigger=CronTrigger(minute='3,13,23,33,43,53'),
        id='player_summary_reconcile',
        name='选手赛季 AI 点评增量对账',
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=45),
    )
    logger.info('选手赛季 AI 点评对账任务已添加：每 10 分钟增量检查')

    return scheduler


def _active_cup_names(champion_only=False):
    seasons = Season.get_active()
    if champion_only:
        seasons = [s for s in seasons if s.get('champion_enabled')]
    return {s['cup_name'] for s in seasons}


def judge_all_champions():
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    for cup_name in _active_cup_names(champion_only=True):
        try:
            judge_champion(yesterday, cup_name)
        except Exception as e:
            logger.error(f"判断 {cup_name} {yesterday} 冠军失败: {e}")


def calc_titles(today):
    try:
        for cup_name in _active_cup_names():
            season_success = title_service.calculate_and_save_titles(cup_name)
            day_success = title_service.calculate_and_save_titles(cup_name, today)
            if season_success:
                logger.info(f"成功更新 {cup_name} 赛季称号")
            if day_success:
                logger.info(f"成功更新 {cup_name} {today} 比赛日称号")
    except Exception as e:
        logger.error(f"计算称号失败: {str(e)}")


if __name__ == '__main__':
    load_dotenv()
    create_tables()
    # calc_titles('20250923')
    # judge_champion('20250925')
    crawl_all()
    scheduler = create_scheduler()
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("调度器已停止")
