# 配置日志
import datetime
import json
import time

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from ajlog import logger
from champion_service import judge_champion

from database import (create_tables, Match, MatchPlayer, Player, Config,
                      Season, SeasonRoster, MatchSelection)
from title_service import title_service
from utils import get_play_day
from wm import WMAPI


def _store_match(match_data, assigned_cup_name=None, play_day=None):
    """把一场比赛详情入库（Match + MatchPlayer + Player）。

    assigned_cup_name：官方比赛传 API cupName；自定义候选传 None（待管理员确认后回填赛季 cup_name）。
    play_day：已算好的比赛日（自定义候选路径传入）；未传则按 -3h 比赛日计算。
    """
    match_base_info = match_data.get('base', {})
    match_id = match_base_info.get('matchId')
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
    elif assigned_cup_name and existing.get('cup_name') != assigned_cup_name:
        Match.update(cup_name=assigned_cup_name).where(Match.match_id == match_id).execute()
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
            "pvp_team": match_player.get('pvpTeam'),
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
        }

        if match_model.get("play_day") is not None:
            match_player_model['play_day'] = match_model.get("play_day")

        if not MatchPlayer.is_exist(match_id, player_id):
            MatchPlayer.create(**match_player_model)

        player_model = {
            "player_id": player_id,
            "nickname": match_player.get('nickName'),
            "avatar": match_player.get('avatar')
        }

        if not Player.is_exist(player_id):
            player_model['in_library'] = False
            Player.create(**player_model)
            logger.info(f"玩家 {player_id} 已保存（非库内）")

    return match_id


def _in_season_window(season, play_day):
    """判断某比赛日是否落在赛季时间段内（闭区间，YYYYMMDD 字符串比较）"""
    if not play_day:
        return False
    start = season.get('start_date')
    end = season.get('end_date')
    if start and play_day < start:
        return False
    if end and play_day > end:
        return False
    return True


def _new_wm():
    return WMAPI(token='c27dd7695e6913c414a018601470e48426c96805', token_steam_id='76561198256708927')


def _library_hit(player_ids, library_ids):
    if not player_ids:
        return 0, 0.0
    hit = len(set(player_ids) & library_ids)
    return hit, hit / len(player_ids)


def crawl_data(default_player_id='76561198068647788'):
    """兼容：爬单个玩家近期官方比赛，仅入库 active official 赛季。"""
    wm = _new_wm()
    match_list = wm.get_match_list(default_player_id, 10)
    official_cups = {s['cup_name'] for s in Season.get_active_by_type('official')}
    if not official_cups:
        return

    for match in match_list:
        match_id = match.get('matchId')
        cup_name = match.get('cupName')
        if not cup_name or cup_name not in official_cups:
            continue
        match_data = wm.get_match(match_id)
        if match_data:
            _store_match(match_data, assigned_cup_name=cup_name)


def get_crawl_status(cup_name):
    raw = Config.get_value(f'crawl_status:{cup_name}')
    if not raw:
        return {'state': 'idle'}
    try:
        return json.loads(raw)
    except Exception:
        return {'state': 'idle', 'message': raw}


def set_crawl_status(cup_name, **fields):
    current = get_crawl_status(cup_name)
    current.update(fields)
    Config.set_value(f'crawl_status:{cup_name}', json.dumps(current, ensure_ascii=False))


def crawl_season_with_status(cup_name):
    season = Season.get_by_cup(cup_name)
    if not season:
        raise ValueError(f'赛季不存在: {cup_name}')
    set_crawl_status(
        cup_name,
        state='running',
        message='采集中',
        started_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        finished_at=None,
        stats=None,
    )
    try:
        stats = crawl_season(season)
        set_crawl_status(
            cup_name,
            state='done',
            message=f"完成：访问 {stats.get('visited')} 人，纳入 {stats.get('included')} 场，跳过 {stats.get('skipped')} 场",
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            stats=stats,
        )
        Config.set_value("last_crawl_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        return stats
    except Exception as e:
        set_crawl_status(
            cup_name,
            state='error',
            message=str(e),
            finished_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        raise


def crawl_season(season):
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

    seeds = SeasonRoster.get_player_ids(cup_name)
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
        pid = queue.pop(0)
        if pid in visited:
            continue
        visited.add(pid)
        try:
            match_list = wm.get_match_list(pid, 100, older_than_day=season.get('start_date'))
        except Exception as e:
            logger.error(f"拉取玩家 {pid} 比赛列表失败: {e}")
            time.sleep(10)
            continue

        for match in match_list:
            match_id = match.get('matchId')
            if not match_id or match_id in seen_matches:
                continue
            seen_matches.add(match_id)

            play_day = get_play_day(match.get('endTime'), 3)
            if not _in_season_window(season, play_day):
                continue

            api_cup = match.get('cupName') or ''
            if match_type == 'official':
                if api_cup != cup_name:
                    continue
            else:
                if api_cup:
                    continue

            match_data = wm.get_match(match_id)
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
                _store_match(match_data, assigned_cup_name=cup_name, play_day=play_day)
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
    Config.set_value("last_crawl_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    today = (datetime.datetime.now() - datetime.timedelta(hours=3)).strftime("%Y%m%d")
    seasons = Season.get_active()

    logger.info(f"====== 开始采集 active 赛季 {len(seasons)} 个，今日 {today} ======")
    for season in seasons:
        try:
            crawl_season(season)
        except Exception as e:
            logger.error(f"采集赛季 {season.get('cup_name')} 失败: {e}")

    logger.info(f"====== 采集完成 ======")
    calc_titles(today)



def create_scheduler():
    executors = {
        'default': ThreadPoolExecutor(max_workers=5)  # 根据需要调整数量
    }

    scheduler = BlockingScheduler(executors=executors)

    # 添加任务
    scheduler.add_job(
        func=crawl_all,
        trigger=CronTrigger(hour='18-23', minute='*/10'),
        id='crawl_job_evening',
        name='数据爬取任务-晚间',
        replace_existing=True
    )

    # 00:00-05:50 (次日凌晨)
    scheduler.add_job(
        func=crawl_all,
        trigger=CronTrigger(hour='0-5', minute='*/10'),
        id='crawl_job_night',
        name='数据爬取任务-凌晨',
        replace_existing=True
    )
    logger.info("调度器已创建，任务已添加")

    scheduler.add_job(
        func=judge_all_champions,
        trigger=CronTrigger(hour='0-2', minute='*/5'),
        id='job_judge_champion',
        name='冠军判断任务',
        replace_existing=True
    )

    return scheduler


def _active_cup_names():
    return {s['cup_name'] for s in Season.get_active()}


def judge_all_champions():
    yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    for cup_name in _active_cup_names():
        try:
            judge_champion(yesterday, cup_name)
        except Exception as e:
            logger.error(f"判断 {cup_name} {yesterday} 冠军失败: {e}")


def calc_titles(today):
    try:
        for cup_name in _active_cup_names():
            success = title_service.calculate_and_save_titles(cup_name, today)
            if success:
                logger.info(f"成功计算 {cup_name} {today} 的称号")
            else:
                logger.error(f"计算 {cup_name} {today} 称号失败")
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
