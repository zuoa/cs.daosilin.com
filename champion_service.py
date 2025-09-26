import datetime

from ajlog import logger
from config import CUP_NAME
from database import Match, CupDayChampion, MatchPlayer


def judge_champion(day=None, cup_name=None):
    if day is None:
        day = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")

    if cup_name is None:
        cup_name = CUP_NAME
    match_list = Match.filter_records(**{'cup_name': cup_name, 'play_day': day})
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

        champion_players = MatchPlayer.filter_records \
            (**{'cup_name': cup_name, 'play_day': day, 'team_name': champion_team})
        if champion_players:
            champion_players_map = {
                player['player_id']: player for player in champion_players
            }
            champion_player_ids = ','.join([pk for pk in champion_players_map.keys()])
            logger.info(f"冠军队伍 {champion_team} 的成员有： {champion_player_ids} ")

        if runner_up_team:
            runner_up_players = MatchPlayer.filter_records \
                (**{'cup_name': cup_name, 'play_day': day, 'team_name': runner_up_team})
            if runner_up_players:
                runner_up_players_map = {
                    player['player_id']: player for player in runner_up_players
                }
                runner_up_player_ids = ','.join([pk for pk in runner_up_players_map.keys()])
                logger.info(f"亚军队伍 {runner_up_team} 的成员有： {runner_up_player_ids} ")

        # 保存冠军和亚军信息到数据库
        if CupDayChampion.is_exist(cup_name, day):
            logger.info(f"{day} 的冠军信息已存在，跳过保存")
            return

        CupDayChampion.create(**{
            'cup_name': cup_name,
            'day': day,
            'champion_team_name': champion_team,
            'runner_up_team_name': runner_up_team,
            'champion_team_player_ids': champion_player_ids,
            'runner_up_team_player_ids': runner_up_player_ids
        })

    else:
        logger.info("昨日没有比赛数据，无法判断冠军队伍")
