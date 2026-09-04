import datetime
import unicodedata
from collections import defaultdict

from ajlog import logger
from cache_service import invalidate_season
from database import Match, CupDayChampion, MatchPlayer


def _team_key(name):
    """Return a stable comparison key while retaining the recorded team name."""
    return ' '.join(unicodedata.normalize('NFKC', str(name or '')).split()).casefold()


def _canonical_match_id(match_id):
    """Normalize the two WMPVP ID forms found in historical match records."""
    value = str(match_id or '').strip()
    prefix, separator, suffix = value.partition('@')
    if separator and prefix.upper() == 'PVP' and suffix.isdigit():
        return suffix
    return value


def _score(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _map_winner(match, team1, team2):
    score1 = _score(match.get('team1_score'))
    score2 = _score(match.get('team2_score'))
    if score1 is not None and score2 is not None and score1 != score2:
        return team1 if score1 > score2 else team2

    # Scores are normally sufficient, but win_team lets imported records with
    # missing scores remain usable. A tied score is never treated as finished.
    if score1 is not None and score2 is not None:
        return None
    win_team = _score(match.get('win_team'))
    if win_team == 1:
        return team1
    if win_team == 2:
        return team2
    return None


def _match_sort_key(indexed_match):
    index, match = indexed_match
    return (
        str(match.get('end_time') or match.get('start_time') or ''),
        str(match.get('start_time') or ''),
        index,
    )


def _completed_bo3_series(match_list):
    """Collapse map records into chronological, completed best-of-three series."""
    unique_matches = []
    seen_match_ids = set()
    for index, match in enumerate(match_list):
        match_id = _canonical_match_id(match.get('match_id'))
        if match_id and match_id in seen_match_ids:
            continue
        if match_id:
            seen_match_ids.add(match_id)
        unique_matches.append((index, match))

    active = {}
    completed = []
    display_names = {}
    for _, match in sorted(unique_matches, key=_match_sort_key):
        team1_name = ' '.join(str(match.get('team1_name') or '').split())
        team2_name = ' '.join(str(match.get('team2_name') or '').split())
        team1 = _team_key(team1_name)
        team2 = _team_key(team2_name)
        if not team1 or not team2 or team1 == team2:
            continue

        winner = _map_winner(match, team1, team2)
        if winner is None:
            continue

        display_names[team1] = team1_name
        display_names[team2] = team2_name
        pairing = frozenset((team1, team2))
        series = active.setdefault(pairing, {
            'teams': (team1, team2),
            'wins': defaultdict(int),
            'map_count': 0,
        })
        series['wins'][winner] += 1
        series['map_count'] += 1

        if series['wins'][winner] == 2:
            loser = team2 if winner == team1 else team1
            completed.append({
                'winner': winner,
                'loser': loser,
                'teams': pairing,
                'score': (2, series['wins'][loser]),
                'map_count': series['map_count'],
                'completed_at': match.get('end_time'),
            })
            # The same teams could meet again later. Once a BO3 is won, future
            # maps form a new series instead of being merged into this one.
            del active[pairing]

    return completed, display_names


def calculate_daily_podium(match_list):
    """Resolve a day's champion and runner-up from the eight-team BO3 format.

    The first series for each team is round one. In round two, teams may only
    meet an opponent with the same round-one record. The two 2-0 teams then
    play the final. A result is returned only when all four round-one series,
    all four round-two series, and the final are complete.
    """
    series_list, display_names = _completed_bo3_series(match_list)
    histories = defaultdict(list)
    round_one = []
    round_two = []
    finals = []

    for series in series_list:
        winner = series['winner']
        loser = series['loser']
        winner_history = histories[winner]
        loser_history = histories[loser]

        if not winner_history and not loser_history:
            round_one.append(series)
        elif (
            len(winner_history) == len(loser_history) == 1
            and winner_history[0] == loser_history[0]
        ):
            round_two.append(series)
        elif winner_history == ['W', 'W'] and loser_history == ['W', 'W']:
            finals.append(series)
        else:
            # This pairing does not belong to the advertised daily format.
            # Do not let it manufacture a 2-0 path for a later match.
            continue

        histories[winner].append('W')
        histories[loser].append('L')

    round_one_teams = set().union(*(s['teams'] for s in round_one)) if round_one else set()
    round_two_teams = set().union(*(s['teams'] for s in round_two)) if round_two else set()
    if (
        len(round_one) != 4
        or len(round_one_teams) != 8
        or len(round_two) != 4
        or round_two_teams != round_one_teams
        or len(finals) != 1
    ):
        return None

    final = finals[0]
    return {
        'champion_team': display_names[final['winner']],
        'runner_up_team': display_names[final['loser']],
        'series_count': len(series_list),
        'final_score': final['score'],
    }


def _player_ids_by_team(cup_name, day):
    players = MatchPlayer.filter_records(**{
        'cup_name': cup_name,
        'play_day': day,
    })
    grouped = defaultdict(dict)
    for player in players:
        team = _team_key(player.get('team_name'))
        player_id = player.get('player_id')
        if team and player_id is not None:
            grouped[team][str(player_id)] = None
    return {team: ','.join(player_ids) for team, player_ids in grouped.items()}


def judge_champion(day=None, cup_name=None):
    if day is None:
        day = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime('%Y%m%d')

    if not cup_name:
        logger.warning('judge_champion 未指定 cup_name，跳过')
        return None

    match_list = Match.filter_records(**{'cup_name': cup_name, 'play_day': day})
    if not match_list:
        logger.info(f'{cup_name} {day} 没有比赛记录，跳过冠军判断')
        return None

    podium = calculate_daily_podium(match_list)
    if not podium:
        completed_series, _ = _completed_bo3_series(match_list)
        logger.info(
            f'{cup_name} {day} 已记录 {len(match_list)} 张地图、'
            f'{len(completed_series)} 个完整 BO3，赛制尚未完整，暂不生成冠亚军'
        )
        return None

    champion_team = podium['champion_team']
    runner_up_team = podium['runner_up_team']
    logger.info(
        f'{cup_name} {day} 冠军 {champion_team}，亚军 {runner_up_team}，'
        f'决赛 {podium["final_score"][0]}-{podium["final_score"][1]}'
    )

    player_ids_by_team = _player_ids_by_team(cup_name, day)
    champion_player_ids = player_ids_by_team.get(_team_key(champion_team), '')
    runner_up_player_ids = player_ids_by_team.get(_team_key(runner_up_team), '')
    values = {
        'cup_name': cup_name,
        'day': day,
        'champion_team_name': champion_team,
        'runner_up_team_name': runner_up_team,
        'champion_team_player_ids': champion_player_ids,
        'runner_up_team_player_ids': runner_up_player_ids,
    }
    if CupDayChampion.is_exist(cup_name, day):
        existing = CupDayChampion.get_champion_by_cup_and_day(cup_name, day) or {}
        changed = any(existing.get(field) != value for field, value in values.items())
        if not changed:
            logger.info(f'{cup_name} {day} 的冠亚军信息未变化')
            return podium
        (CupDayChampion.update(**values)
         .where(CupDayChampion.cup_name == cup_name, CupDayChampion.day == day)
         .execute())
        logger.info(f'{cup_name} {day} 的冠亚军信息已按比赛记录修正')
    else:
        CupDayChampion.create(**values)
    invalidate_season(cup_name, external=False)
    return podium
