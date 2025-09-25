# 配置日志
import datetime
import json
import time

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from ajlog import logger
from config import CUP_NAME, CUP_TEAM_NUM, DEFAULT_CRAWL_PLAYER_IDS
from database import create_tables, Match, MatchPlayer, Player, CupDayChampion, Config
from title_service import title_service
from utils import get_play_day
from wm import WMAPI


def crawl_data(default_player_id='76561198068647788'):
    """爬取数据的函数"""
    wm = WMAPI(token='c27dd7695e6913c414a018601470e48426c96805', token_steam_id='76561198256708927')
    print(default_player_id)
    match_list = wm.get_match_list(default_player_id, 10)
    print(match_list)
    for match in match_list:
        match_id = match.get('matchId')

        if match.get('cupName') != CUP_NAME:
            logger.debug(f"比赛 {match_id} 不属于当前杯赛 {CUP_NAME}，跳过")
            continue

        match_data = wm.get_match(match_id)
        if match_data:
            match_base_info = match_data.get('base', {})
            match_model = {
                "match_id": match_base_info.get('matchId'),
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
                "cup_name": match_base_info.get('cupName'),
                "cup_logo": match_base_info.get('cupLogo'),
                "game_mode": match_base_info.get('mode'),
                "notes": json.dumps(match_data, default=str, ensure_ascii=False)
            }

            if match_model.get('cup_name') is not None:
                match_model['play_day'] = get_play_day(match_model.get('end_time'), 3)
            else:
                match_model['play_day'] = get_play_day(match_model.get('end_time'))

            # 检查比赛是否已存在，避免重复插入
            if not Match.get_by_match_id(match_id):
                Match.create(**match_model)
                logger.info(f"比赛 {match_id} 已保存")

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
                    Player.create(**player_model)
                    logger.info(f"玩家 {player_id} 已保存")


def crawl_all():
    Config.set_value("last_crawl_time", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    today = (datetime.datetime.now() - datetime.timedelta(hours=3)).strftime("%Y%m%d")
    logger.info(f"====== 开始爬取所有玩家数据：{CUP_NAME} {today} ======")
    today_players = MatchPlayer.filter_records(**{'cup_name': CUP_NAME, 'play_day': today})
    total_player_count = 0
    # 过滤重复player_id
    if today_players:
        unique_player_ids = set()
        for player in today_players:
            if player['player_id'] not in unique_player_ids:
                unique_player_ids.add(player['player_id'])
        total_player_count = len(unique_player_ids)

    if total_player_count >= 5 * CUP_TEAM_NUM:
        logger.info(f"今日已爬取玩家数 {total_player_count}，满足要求，开始爬取")
        match_id_loaded = set()
        player_id_loaded = set()
        for player in today_players:
            if player['player_id'] in player_id_loaded:
                logger.debug(f"玩家 {player['player_id']} 已爬取，跳过")
                continue
            player_id_loaded.add(player['player_id'])

            if player['match_id'] in match_id_loaded:
                logger.debug(f"比赛 {player['match_id']} 已爬取，跳过")
                continue
            match_id_loaded.add(player['match_id'])
            crawl_data(player['player_id'])
            time.sleep(10)
    else:
        players = Player.get_all()
        if not players:
            pids = DEFAULT_CRAWL_PLAYER_IDS.split(';')
            players = [{'player_id': pid.strip()} for pid in pids]
            logger.info(f"没有找到任何玩家，使用默认玩家ID列表，共 {len(players)} 个玩家")

        for player in players:
            crawl_data(player['player_id'])
            time.sleep(10)

    logger.info(f"====== 所有玩家数据爬取完成：{CUP_NAME} {today} ======")

    calc_titles(today)


def judge_champion(day=None):
    if day is None:
        day = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    match_list = Match.filter_records(**{'cup_name': CUP_NAME, 'play_day': day})
    team_wins = {}

    # 比赛分几轮，每一轮对阵会有2-3场比赛，取得2场胜利的队伍为该轮胜者，然后进入下一轮，最终轮的胜者为冠军,冠军的对手就是亚军。不是简单统计胜场多的
    # 还需要算出亚军，冠军的最后一轮的对手就是亚军
    rounds = {}
    for match in match_list:
        team1 = match.get('team1_name')
        team2 = match.get('team2_name')
        win_team = team1 if match.get('team1_score') > match.get('team2_score') else team2
        if not team1 or not team2 or not win_team:
            continue

        round_key = frozenset([team1, team2])
        if round_key not in rounds:
            rounds[round_key] = {team1: 0, team2: 0}
        rounds[round_key][win_team] += 1

    # 计算每个队伍的胜场数
    for teams, results in rounds.items():
        for team, wins in results.items():
            if wins >= 2:
                team_wins[team] = team_wins.get(team, 0) + 1

    if team_wins:
        # 计算冠军,需要比赛了三轮了才算， 计算team_wins中value最大有没有超过等于3的
        if max(team_wins.values()) < 3:
            logger.info("昨日比赛未完成三轮，无法判断冠军队伍")
            return

        champion_player_ids = ''
        runner_up_player_ids = ''
        champion_team = max(team_wins, key=team_wins.get)
        logger.info(f"昨日冠军队伍是 {champion_team}，共赢得 {team_wins[champion_team]} 轮比赛")

        # 计算亚军
        runner_up_team = None
        champion_rounds = [teams for teams in rounds.keys() if champion_team in teams]
        if champion_rounds:
            # 找到冠军队伍参与的最后一轮（决赛轮）
            # 通过查找包含冠军队伍且比赛时间最晚的轮次来确定决赛轮
            final_round = None
            latest_match_time = None
            
            for round_teams in champion_rounds:
                # 找到这一轮中冠军队伍参与的比赛的最晚时间
                round_matches = [match for match in match_list 
                               if match.get('team1_name') in round_teams and match.get('team2_name') in round_teams]
                if round_matches:
                    # 获取这一轮比赛的最晚结束时间
                    round_latest_time = max(match.get('end_time', 0) for match in round_matches)
                    if latest_match_time is None or round_latest_time > latest_match_time:
                        latest_match_time = round_latest_time
                        final_round = round_teams
            
            if final_round:
                # 在决赛轮中找到冠军队伍的对手作为亚军
                runner_up_team = list(final_round - {champion_team})[0]
                logger.info(f"昨日亚军队伍是 {runner_up_team}")

        champion_players = MatchPlayer.filter_records(**{'cup_name': CUP_NAME, 'play_day': day, 'team_name': champion_team})
        if champion_players:
            champion_players_map = {
                player['player_id']: player for player in champion_players
            }
            champion_player_ids = ','.join([pk for pk in champion_players_map.keys()])
            logger.info(f"冠军队伍 {champion_team} 的成员有： {champion_player_ids} ")

        if runner_up_team:
            runner_up_players = MatchPlayer.filter_records(**{'cup_name': CUP_NAME, 'play_day': day, 'team_name': runner_up_team})
            if runner_up_players:
                runner_up_players_map = {
                    player['player_id']: player for player in runner_up_players
                }
                runner_up_player_ids = ','.join([pk for pk in runner_up_players_map.keys()])
                logger.info(f"亚军队伍 {runner_up_team} 的成员有： {runner_up_player_ids} ")

        # 保存冠军和亚军信息到数据库
        if CupDayChampion.is_exist(CUP_NAME, day):
            logger.info(f"{day} 的冠军信息已存在，跳过保存")
            return

        CupDayChampion.create(**{
            'cup_name': CUP_NAME,
            'day': day,
            'champion_team_name': champion_team,
            'runner_up_team_name': runner_up_team,
            'champion_team_player_ids': champion_player_ids,
            'runner_up_team_player_ids': runner_up_player_ids
        })

    else:
        logger.info("昨日没有比赛数据，无法判断冠军队伍")


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
        func=judge_champion,
        trigger=CronTrigger(hour='0-2', minute='*/5'),
        id='job_judge_champion',
        name='冠军判断任务',
        replace_existing=True
    )

    return scheduler


def calc_titles(today):
    try:
        # 获取杯赛名称（从配置或数据库）
        cup_name = CUP_NAME

        # 计算整个杯赛的称号
        # success = title_service.calculate_and_save_titles(cup_name)
        # if success:
        #     logger.info(f"成功计算 {cup_name} 的称号")
        # else:
        #     logger.error(f"计算 {cup_name} 称号失败")

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
    scheduler = create_scheduler()
    try:
        scheduler.start()
    except KeyboardInterrupt:
        print("调度器已停止")
