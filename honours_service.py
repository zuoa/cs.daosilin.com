"""Deterministic season honour boards for the public CS2 archive."""

from __future__ import annotations

import math
import json
import statistics
import threading
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from typing import Any, Callable

from baokemeng_service import draft_pick_summaries
from champion_service import (_player_ids_by_team, _team_aliases_from_players,
                              opening_round_loser_teams)
from community_rating_service import community_rating_summaries
from database import (CupDayChampion, ManualHonourAward, Match, MatchPlayer,
                      Player, Season, SeasonHonourSnapshot, SeasonRoster)


CATEGORIES = (
    ('podium', '领奖台常客'),
    ('schedule', '赛程体验'),
    ('form', '状态曲线'),
    ('contrast', '反差观察'),
    ('match', '对局人物'),
    ('specialist', '技术偏科'),
    ('chemistry', '搭档化学'),
    ('side', '阵营天赋'),
)

MANUAL_CATEGORY = ('manual', '评审特别奖')
_snapshot_lock = threading.RLock()


class HonourValidationError(ValueError):
    pass


def _number(value: object) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat(timespec='seconds')
    return str(value)


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    """Return 0–1 percentiles with average ranks for ties."""
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 0.5}
    result = {}
    candidates = list(values.items())
    for player_id, value in candidates:
        lower = sum(candidate < value for _, candidate in candidates)
        equal = sum(candidate == value for _, candidate in candidates)
        result[player_id] = (lower + (equal - 1) / 2) / (len(candidates) - 1)
    return result


def _minimum_matches(players: dict[str, dict[str, Any]]) -> int:
    maximum = max((int(player.get('match_count') or 0) for player in players.values()), default=0)
    if maximum <= 3:
        return 1
    return max(3, math.ceil(maximum * 0.30))


def _season_start(cup: str, season: dict[str, Any]) -> datetime | None:
    value = season.get('start_date')
    if isinstance(value, datetime):
        return value
    if value:
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00')).replace(tzinfo=None)
        except ValueError:
            pass
    row = (Match.select(Match.start_time)
           .where(Match.cup_name == cup)
           .order_by(Match.start_time)
           .first())
    return row.start_time if row else None


def _is_final(season: dict[str, Any]) -> bool:
    if season.get('status') == 'archived':
        return True
    end_date = season.get('end_date')
    if isinstance(end_date, datetime):
        return end_date <= datetime.now()
    if end_date:
        try:
            return datetime.fromisoformat(str(end_date).replace('Z', '+00:00')).replace(tzinfo=None) <= datetime.now()
        except ValueError:
            return False
    return False


def _profile_name(profile: dict[str, Any], fallback: dict[str, Any], player_id: str) -> str:
    return str(
        profile.get('alias_name') or profile.get('nickname')
        or fallback.get('nickname') or player_id
    )


def _history_by_player(
    cup: str,
    player_ids: list[str],
    account_map: dict[str, str],
    start: datetime | None,
) -> dict[str, dict[str, float]]:
    if not player_ids or start is None:
        return {}
    account_ids = [
        account_id for account_id, canonical_id in account_map.items()
        if canonical_id in player_ids
    ]
    account_ids.extend(player_id for player_id in player_ids if player_id not in account_map)
    rows = (MatchPlayer
            .select(MatchPlayer.player_id, MatchPlayer.pw_rating)
            .join(
                Match,
                on=((MatchPlayer.match_id == Match.match_id)
                    & (MatchPlayer.cup_name == Match.cup_name)),
            )
            .where(
                MatchPlayer.player_id.in_(list(dict.fromkeys(account_ids))),
                MatchPlayer.cup_name.is_null(False),
                MatchPlayer.cup_name != cup,
                Match.start_time < start,
            ))
    totals = defaultdict(lambda: {'sum': 0.0, 'matches': 0})
    for row in rows:
        rating = _number(row.pw_rating)
        if rating <= 0:
            continue
        canonical_id = account_map.get(str(row.player_id), str(row.player_id))
        totals[canonical_id]['sum'] += rating
        totals[canonical_id]['matches'] += 1
    return {
        player_id: {
            'rating': item['sum'] / item['matches'],
            'matches': item['matches'],
        }
        for player_id, item in totals.items() if item['matches']
    }


def _opening_loss_counts(cup: str, days: list[str], account_map: dict[str, str]) -> dict[str, int]:
    counts = defaultdict(int)
    for day in days:
        day_players = MatchPlayer.filter_records(cup_name=cup, play_day=day)
        aliases, _ = _team_aliases_from_players(day_players)
        losers = opening_round_loser_teams(
            Match.filter_records(cup_name=cup, play_day=day), aliases,
        )
        players_by_team = _player_ids_by_team(day_players, aliases)
        for team in losers:
            for raw_player_id in players_by_team.get(team, '').split(','):
                if raw_player_id:
                    counts[account_map.get(raw_player_id, raw_player_id)] += 1
    return dict(counts)


def _award(
    *,
    key: str,
    category: str,
    title: str,
    description: str,
    method: str,
    players: dict[str, dict[str, Any]],
    metric: str,
    eligible: Callable[[dict[str, Any]], bool],
    display: Callable[[dict[str, Any]], str],
    evidence: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    candidates = [
        player for player in players.values()
        if player.get(metric) is not None and eligible(player)
    ]
    candidates.sort(key=lambda player: (
        -_number(player.get(metric)),
        -_number(player.get(f'{metric}_sample')),
        -_number(player.get('avg_pw_rating')),
        str(player.get('name') or '').casefold(),
        str(player.get('player_id') or ''),
    ))
    value_counts = defaultdict(int)
    for player in candidates:
        value_counts[round(_number(player.get(metric)), 10)] += 1
    entries = []
    for position, player in enumerate(candidates[:3], start=1):
        value = _number(player.get(metric))
        entries.append({
            'position': position,
            'player_id': player['player_id'],
            'name': player['name'],
            'avatar': player.get('avatar') or '',
            'value': round(value, 4),
            'display_value': display(player),
            'evidence': evidence(player),
            'tied': value_counts[round(value, 10)] > 1,
        })
    return {
        'key': key,
        'category': category,
        'title': title,
        'description': description,
        'method': method,
        'status': 'ready' if entries else 'collecting',
        'entries': entries,
    }


def _pair_records(
    rows: list[dict[str, Any]],
    account_map: dict[str, str],
    players: dict[str, dict[str, Any]],
) -> dict[tuple[str, str], dict[str, int]]:
    """Count maps and wins for canonical player pairs on the same team."""
    lineups = defaultdict(lambda: {'players': set(), 'win': False})
    for row in rows:
        player_id = account_map.get(
            str(row.get('player_id') or ''), str(row.get('player_id') or ''),
        )
        match_id = str(row.get('match_id') or '')
        team = str(row.get('team') or '')
        if not player_id or player_id not in players or not match_id or not team:
            continue
        lineup = lineups[(match_id, team)]
        lineup['players'].add(player_id)
        lineup['win'] = lineup['win'] or int(row.get('win') or 0) == 1

    result = defaultdict(lambda: {'matches': 0, 'wins': 0})
    for lineup in lineups.values():
        for pair in combinations(sorted(lineup['players']), 2):
            result[pair]['matches'] += 1
            result[pair]['wins'] += int(lineup['win'])
    return dict(result)


def _pair_award(
    *,
    key: str,
    title: str,
    description: str,
    method: str,
    pair_records: dict[tuple[str, str], dict[str, int]],
    players: dict[str, dict[str, Any]],
    minimum_maps: int,
    lowest: bool = False,
) -> dict[str, Any]:
    candidates = []
    for pair, stats in pair_records.items():
        matches = int(stats.get('matches') or 0)
        if matches < minimum_maps:
            continue
        wins = int(stats.get('wins') or 0)
        candidates.append({
            'pair': pair,
            'matches': matches,
            'wins': wins,
            'win_rate': wins / matches if matches else 0.0,
        })
    candidates.sort(key=lambda item: (
        item['win_rate'] if lowest else -item['win_rate'],
        -item['matches'],
        tuple((players.get(player_id) or {}).get('name') or player_id for player_id in item['pair']),
        item['pair'],
    ))
    value_counts = defaultdict(int)
    for candidate in candidates:
        value_counts[round(candidate['win_rate'], 10)] += 1

    entries = []
    for position, candidate in enumerate(candidates[:3], start=1):
        members = [
            {
                'player_id': player_id,
                'name': players[player_id]['name'],
                'avatar': players[player_id].get('avatar') or '',
            }
            for player_id in candidate['pair']
        ]
        losses = candidate['matches'] - candidate['wins']
        entries.append({
            'position': position,
            'player_id': '+'.join(candidate['pair']),
            'name': ' × '.join(member['name'] for member in members),
            'avatar': '',
            'members': members,
            'value': round(candidate['win_rate'], 4),
            'display_value': f"{candidate['win_rate'] * 100:.1f}% 胜率",
            'evidence': f"同队 {candidate['matches']} 张地图 · {candidate['wins']} 胜 {losses} 负",
            'tied': value_counts[round(candidate['win_rate'], 10)] > 1,
        })
    return {
        'key': key,
        'category': 'chemistry',
        'title': title,
        'description': description,
        'method': method,
        'status': 'ready' if entries else 'collecting',
        'entries': entries,
    }


def _planned_side_award(key: str, title: str, description: str) -> dict[str, Any]:
    return {
        'key': key,
        'category': 'side',
        'title': title,
        'description': description,
        'method': '需要逐回合记录选手所在的 CT/T 阵营及该阵营表现。当前整图聚合数据无法可靠计算。',
        'status': 'data_required',
        'entries': [],
    }


def _calculate_season_honours(cup: str) -> dict[str, Any]:
    season = Season.get_by_cup(cup) or {}
    cup_alias = season.get('cup_alias') or season.get('name') or season.get('cup_name') or cup
    account_map = Player.account_map()
    raw_rows = MatchPlayer.filter_records(cup_name=cup)
    fallback_by_player = {}
    player_ids = []
    for row in raw_rows:
        player_id = account_map.get(str(row.get('player_id') or ''), str(row.get('player_id') or ''))
        if not player_id:
            continue
        if player_id not in fallback_by_player:
            fallback_by_player[player_id] = row
            player_ids.append(player_id)

    profiles = {
        str(row['player_id']): row
        for row in Player.select().where(Player.parent_player_id.is_null(True)).dicts()
    }
    aggregate_map = MatchPlayer.get_match_exploits(
        cup, player_ids, identity_map=account_map,
    )
    players = {}
    for player_id in player_ids:
        stats = aggregate_map.get(player_id)
        if not stats:
            continue
        profile = profiles.get(player_id, {})
        fallback = fallback_by_player.get(player_id, {})
        players[player_id] = {
            **stats,
            'player_id': player_id,
            'name': _profile_name(profile, fallback, player_id),
            'avatar': profile.get('avatar') or fallback.get('avatar') or '',
            'perfect_score': profile.get('perfect_score'),
            'perfect_level': profile.get('perfect_level'),
        }

    days = sorted(str(day) for day in (MatchPlayer.get_cup_day_set(cup) or []) if day)
    day_map = MatchPlayer.get_match_exploits_by_day(cup, player_ids) if player_ids else {}
    day_ratings = defaultdict(list)
    day_counts = defaultdict(int)
    for player_id in player_ids:
        for day in days:
            stats = day_map.get((player_id, day))
            if not stats:
                continue
            day_counts[player_id] += 1
            rating = _number(stats.get('avg_pw_rating'))
            if rating > 0:
                day_ratings[player_id].append(rating)

    champions = defaultdict(int)
    runners_up = defaultdict(int)
    for podium in CupDayChampion.filter_records(cup_name=cup):
        for raw_player_id in str(podium.get('champion_team_player_ids') or '').split(','):
            if raw_player_id:
                champions[account_map.get(raw_player_id, raw_player_id)] += 1
        for raw_player_id in str(podium.get('runner_up_team_player_ids') or '').split(','):
            if raw_player_id:
                runners_up[account_map.get(raw_player_id, raw_player_id)] += 1

    opening_losses = _opening_loss_counts(cup, days, account_map)
    history = _history_by_player(cup, player_ids, account_map, _season_start(cup, season))
    draft_stats = draft_pick_summaries(days, player_ids)
    community = community_rating_summaries(cup, player_ids) if player_ids else {}

    losing_rating = defaultdict(lambda: {'sum': 0.0, 'matches': 0})
    for row in raw_rows:
        if int(row.get('win') or 0) != 0:
            continue
        rating = _number(row.get('pw_rating'))
        if rating <= 0:
            continue
        player_id = account_map.get(str(row.get('player_id')), str(row.get('player_id')))
        losing_rating[player_id]['sum'] += rating
        losing_rating[player_id]['matches'] += 1

    minimum_matches = _minimum_matches(players)
    generally_eligible = {
        player_id for player_id, player in players.items()
        if int(player.get('match_count') or 0) >= minimum_matches
    }
    pwr_percentiles = _percentiles({
        player_id: _number(player.get('avg_pw_rating'))
        for player_id, player in players.items() if player_id in generally_eligible
    })
    perfect_percentiles = _percentiles({
        player_id: _number(player.get('perfect_score'))
        for player_id, player in players.items()
        if player_id in generally_eligible and _number(player.get('perfect_score')) > 0
    })
    community_percentiles = _percentiles({
        player_id: _number((community.get(player_id) or {}).get('score'))
        for player_id in generally_eligible
        if (community.get(player_id) or {}).get('status') == 'formed'
    })
    pwr_order = sorted(
        generally_eligible,
        key=lambda player_id: (-_number(players[player_id].get('avg_pw_rating')), player_id),
    )
    pwr_ranks = {player_id: index + 1 for index, player_id in enumerate(pwr_order)}

    for player_id, player in players.items():
        player['champion_count'] = champions[player_id]
        player['runner_up_count'] = runners_up[player_id]
        player['final_count'] = champions[player_id] + runners_up[player_id]
        player['opening_loss_count'] = opening_losses.get(player_id, 0)
        player['day_count'] = day_counts[player_id]
        ratings = day_ratings[player_id]
        player['rating_volatility'] = statistics.pstdev(ratings) if len(ratings) >= 3 else None
        player['rating_volatility_sample'] = len(ratings)
        past = history.get(player_id)
        if past and past['matches'] >= 3 and int(player.get('match_count') or 0) >= 3:
            delta = _number(player.get('avg_pw_rating')) - past['rating']
            player['history_gain'] = delta if delta > 0 else None
            player['history_drop'] = -delta if delta < 0 else None
            player['history_gain_sample'] = past['matches']
            player['history_drop_sample'] = past['matches']
            player['historical_rating'] = past['rating']
            player['historical_matches'] = past['matches']
        rating_summary = community.get(player_id) or {}
        player['community_score'] = rating_summary.get('score')
        player['community_label'] = rating_summary.get('label')
        player['community_votes'] = rating_summary.get('total_votes') or 0
        if player_id in perfect_percentiles and player_id in community_percentiles:
            player['perfect_community_gap'] = abs(
                perfect_percentiles[player_id] - community_percentiles[player_id]
            )
            player['perfect_community_gap_sample'] = player['community_votes']
            player['perfect_percentile'] = perfect_percentiles[player_id]
            player['community_percentile'] = community_percentiles[player_id]
        if player_id in pwr_percentiles and player_id in community_percentiles:
            player['data_community_gap'] = abs(
                pwr_percentiles[player_id] - community_percentiles[player_id]
            )
            player['data_community_gap_sample'] = player['community_votes']
            player['pwr_percentile'] = pwr_percentiles[player_id]
            player['community_percentile'] = community_percentiles[player_id]
        draft = draft_stats.get(player_id) or {}
        if int(draft.get('pick_count') or 0) >= 2 and player_id in pwr_percentiles:
            priority = 1 - _number(draft.get('average_pool_position'))
            outperformance = pwr_percentiles[player_id] - priority
            if outperformance > 0:
                player['draft_outperformance'] = outperformance
                player['draft_outperformance_sample'] = draft['pick_count']
                player['draft_average_pick'] = draft.get('average_overall_pick')
                player['pwr_rank'] = pwr_ranks.get(player_id)
        lost = losing_rating.get(player_id)
        if lost and lost['matches'] >= 3:
            player['losing_pwr'] = lost['sum'] / lost['matches']
            player['losing_pwr_sample'] = lost['matches']
        rounds = _number(player.get('total_rounds'))
        kills = _number(player.get('total_kills'))
        matches = _number(player.get('match_count'))
        if rounds > 0:
            player['first_death_rate'] = _number(player.get('total_first_deaths')) / rounds
            player['team_flash_rate'] = _number(player.get('total_flash_teammate')) / rounds
            player['utility_damage_rate'] = _number(player.get('total_utility_damage')) / rounds
        if kills > 0:
            player['headshot_rate'] = _number(player.get('total_headshots')) / kills
        if matches > 0:
            player['weighted_clutch_rate'] = (
                _number(player.get('total_1v2'))
                + 2 * _number(player.get('total_1v3'))
                + 3 * _number(player.get('total_1v4'))
                + 4 * _number(player.get('total_1v5'))
            ) / matches

    general = lambda player: player['player_id'] in generally_eligible
    positive = lambda field: lambda player: general(player) and _number(player.get(field)) > 0
    count_display = lambda field, unit='次': lambda player: f"{int(_number(player.get(field)))} {unit}"
    decimal_display = lambda field, prefix='': lambda player: f"{prefix}{_number(player.get(field)):.2f}"
    percent_display = lambda field: lambda player: f"{_number(player.get(field)) * 100:.1f}%"
    percentile_display = lambda field: lambda player: f"{_number(player.get(field)) * 100:.1f} 个百分位"
    pair_records = _pair_records(raw_rows, account_map, players)
    maximum_pair_maps = max(
        (int(item.get('matches') or 0) for item in pair_records.values()), default=0,
    )
    minimum_pair_maps = max(3, math.ceil(maximum_pair_maps * 0.30)) if maximum_pair_maps else 3

    awards = [
        _award(key='champion-counter', category='podium', title='金牌柜台',
               description='冠军拿得多，柜台才摆得满。', method='统计赛季内获得每日冠军的次数。',
               players=players, metric='champion_count', eligible=positive('champion_count'),
               display=count_display('champion_count'), evidence=lambda p: f"冠军 {int(p['champion_count'])} 次 · 决赛 {int(p['final_count'])} 次"),
        _award(key='silver-collector', category='podium', title='银牌收藏家',
               description='离冠军最近的位置，也被他坐熟了。', method='统计赛季内获得每日亚军的次数。',
               players=players, metric='runner_up_count', eligible=positive('runner_up_count'),
               display=count_display('runner_up_count'), evidence=lambda p: f"亚军 {int(p['runner_up_count'])} 次 · 冠军 {int(p['champion_count'])} 次"),
        _award(key='final-regular', category='podium', title='决赛常驻嘉宾',
               description='决赛名单换来换去，总能看见这个名字。', method='冠军次数与亚军次数相加。',
               players=players, metric='final_count', eligible=positive('final_count'),
               display=count_display('final_count'), evidence=lambda p: f"冠军 {int(p['champion_count'])} · 亚军 {int(p['runner_up_count'])}"),
        _award(key='opening-exit', category='schedule', title='首轮速通王',
               description='冠军路线的一轮游次数最多。', method='统计每日冠军路线首轮 BO3 失利次数。',
               players=players, metric='opening_loss_count', eligible=positive('opening_loss_count'),
               display=count_display('opening_loss_count'), evidence=lambda p: f"首轮落败 {int(p['opening_loss_count'])} 次"),
        _award(key='hottest-aim', category='form', title='今年枪最硬',
               description='和自己的过去相比，这赛季提升最大。', method='当前赛季 PWR 减去此前所有比赛的加权平均 PWR。',
               players=players, metric='history_gain', eligible=lambda p: p.get('history_gain') is not None,
               display=decimal_display('history_gain', '+'), evidence=lambda p: f"历史 {p['historical_rating']:.2f} → 本季 {_number(p['avg_pw_rating']):.2f}"),
        _award(key='aim-loading', category='form', title='准星还在加载',
               description='历史数据很能打，这赛季手感还没完全上线。', method='此前所有比赛的加权平均 PWR 减去当前赛季 PWR。',
               players=players, metric='history_drop', eligible=lambda p: p.get('history_drop') is not None,
               display=decimal_display('history_drop', '-'), evidence=lambda p: f"历史 {p['historical_rating']:.2f} → 本季 {_number(p['avg_pw_rating']):.2f}"),
        _award(key='rating-heartbeat', category='form', title='Rating 心电图',
               description='状态起伏最大，观赛体验自带悬念。', method='计算至少三个比赛日 PWR 的总体标准差。',
               players=players, metric='rating_volatility', eligible=lambda p: general(p) and p.get('rating_volatility') is not None,
               display=lambda p: f"σ {_number(p['rating_volatility']):.2f}", evidence=lambda p: f"统计 {int(p['rating_volatility_sample'])} 个比赛日"),
        _award(key='rank-filter', category='contrast', title='段位滤镜奖',
               description='平台段位与群友评价，画出了两种印象。', method='比较完美平台分数与正式社区评分在各自人群中的百分位差。',
               players=players, metric='perfect_community_gap', eligible=lambda p: p.get('perfect_community_gap') is not None,
               display=percentile_display('perfect_community_gap'), evidence=lambda p: (
                   f"平台段位更高 · 社区 {p.get('community_label') or '—'}"
                   if p['perfect_percentile'] > p['community_percentile']
                   else f"社区评价更高 · 平台 {p.get('perfect_level') or '—'}"
               )),
        _award(key='data-reputation', category='contrast', title='数据口碑两张脸',
               description='服务器记录和观众印象，没有得出同一个结论。', method='比较赛季 PWR 与正式社区评分在各自人群中的百分位差。',
               players=players, metric='data_community_gap', eligible=lambda p: p.get('data_community_gap') is not None,
               display=percentile_display('data_community_gap'), evidence=lambda p: (
                   f"数据排名更高 · PWR {_number(p['avg_pw_rating']):.2f}"
                   if p['pwr_percentile'] > p['community_percentile']
                   else f"社区评价更高 · {p.get('community_label') or '—'}"
               )),
        _award(key='late-pick-gem', category='contrast', title='末轮淘宝王',
               description='选得靠后，打出来却一点不靠后。', method='用 PWR 百分位减去选人优先级百分位。',
               players=players, metric='draft_outperformance', eligible=lambda p: p.get('draft_outperformance') is not None,
               display=percentile_display('draft_outperformance'), evidence=lambda p: f"PWR 第 {p['pwr_rank']} · 平均全场第 {p['draft_average_pick']:.1f} 顺位"),
        _award(key='losing-svp', category='match', title='败方 SVP 常驻户',
               description='队伍输了，但他的 Rating 没先投降。', method='至少三场败局后，按败局平均 PWR 排名。',
               players=players, metric='losing_pwr', eligible=lambda p: general(p) and p.get('losing_pwr') is not None,
               display=decimal_display('losing_pwr'), evidence=lambda p: f"统计 {int(p['losing_pwr_sample'])} 场败局"),
        _award(key='first-death', category='match', title='白给效率奖',
               description='开局信息拿到了，人也顺便交代了。', method='按首死总数除以总回合数排名。',
               players=players, metric='first_death_rate', eligible=general,
               display=percent_display('first_death_rate'), evidence=lambda p: f"首死 {int(p['total_first_deaths'])} 次 / {int(p['total_rounds'])} 回合"),
        _award(key='team-flash', category='match', title='致盲不分敌我',
               description='闪光覆盖很全面，队友也没落下。', method='按致盲队友总数除以总回合数排名。',
               players=players, metric='team_flash_rate', eligible=general,
               display=percent_display('team_flash_rate'), evidence=lambda p: f"致盲队友 {int(p['total_flash_teammate'])} 次"),
        _award(key='headshot-line', category='specialist', title='爆头生产线',
               description='击杀可以有很多种，他偏爱最短的那种。', method='按爆头击杀数除以总击杀数排名。',
               players=players, metric='headshot_rate', eligible=general,
               display=percent_display('headshot_rate'), evidence=lambda p: f"爆头 {int(p['total_headshots'])} / 击杀 {int(p['total_kills'])}"),
        _award(key='clutch-overtime', category='specialist', title='残局加班王',
               description='队友下班之后，他还在服务器里处理残局。', method='1v2–1v5 分别按 1–4 加权，再除以比赛数。',
               players=players, metric='weighted_clutch_rate', eligible=positive('weighted_clutch_rate'),
               display=decimal_display('weighted_clutch_rate'), evidence=lambda p: f"1v2/3/4/5：{int(p['total_1v2'])}/{int(p['total_1v3'])}/{int(p['total_1v4'])}/{int(p['total_1v5'])}"),
        _award(key='utility-clearance', category='specialist', title='道具不留过夜',
               description='买都买了，绝不带回下一回合。', method='按手雷与燃烧总伤害除以总回合数排名。',
               players=players, metric='utility_damage_rate', eligible=general,
               display=decimal_display('utility_damage_rate'), evidence=lambda p: f"道具总伤害 {int(p['total_utility_damage'])}"),
        _pair_award(key='duo-engine', title='双人成行',
                    description='这两个人一组队，胜率就开始往上走。',
                    method=f'统计同队至少 {minimum_pair_maps} 张地图的二人组合，按共同出场胜率从高到低排名。',
                    pair_records=pair_records, players=players, minimum_maps=minimum_pair_maps),
        _pair_award(key='duo-slump', title='相遇即低谷',
                    description='单看都没问题，一起上场却总差一点意思。',
                    method=f'统计同队至少 {minimum_pair_maps} 张地图的二人组合，按共同出场胜率从低到高排名。',
                    pair_records=pair_records, players=players, minimum_maps=minimum_pair_maps,
                    lowest=True),
        _planned_side_award(
            'best-ct', '警队定海神针',
            '谁更适合站在防守方，要等逐回合阵营数据说话。',
        ),
        _planned_side_award(
            'best-t', '匪帮破局手',
            '谁更适合打进攻方，要等逐回合阵营数据说话。',
        ),
    ]

    return {
        'cup': cup,
        'cup_alias': cup_alias,
        'status': 'final' if _is_final(season) else 'provisional',
        'generated_at': _iso(datetime.now()),
        'eligible_player_count': len(generally_eligible),
        'minimum_matches': minimum_matches,
        'minimum_pair_maps': minimum_pair_maps,
        'available_award_count': sum(award['status'] == 'ready' for award in awards),
        'categories': [{'key': key, 'label': label} for key, label in CATEGORIES],
        'awards': awards,
    }


def _decode_json(value: str, fallback):
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _player_directory(cup: str | None = None) -> list[dict[str, str]]:
    """Return canonical player options, preferring players in the season."""
    account_map = Player.account_map()
    participant_ids = set(SeasonRoster.get_player_ids(cup)) if cup else set()
    fallback = {}
    if cup:
        for row in MatchPlayer.filter_records(cup_name=cup):
            raw_id = str(row.get('player_id') or '')
            player_id = account_map.get(raw_id, raw_id)
            if player_id:
                participant_ids.add(player_id)
                fallback.setdefault(player_id, row)

    query = Player.select().where(Player.parent_player_id.is_null(True))
    if participant_ids:
        query = query.where(Player.player_id.in_(participant_ids))
    result = []
    seen = set()
    for row in query.dicts():
        player_id = str(row['player_id'])
        seen.add(player_id)
        result.append({
            'player_id': player_id,
            'name': _profile_name(row, fallback.get(player_id, {}), player_id),
            'avatar': row.get('avatar') or (fallback.get(player_id) or {}).get('avatar') or '',
        })
    for player_id in sorted(participant_ids - seen):
        row = fallback.get(player_id, {})
        result.append({
            'player_id': player_id,
            'name': _profile_name({}, row, player_id),
            'avatar': row.get('avatar') or '',
        })
    result.sort(key=lambda item: (item['name'].casefold(), item['player_id']))
    return result


def _manual_awards(cup: str) -> list[dict[str, Any]]:
    rows = list(ManualHonourAward.select()
                .where(ManualHonourAward.cup_name == cup)
                .order_by(ManualHonourAward.created_at, ManualHonourAward.id))
    if not rows:
        return []
    decoded = {row.id: _decode_json(row.recipients_json, []) for row in rows}
    recipient_ids = {
        str(recipient.get('player_id') or '')
        for recipients in decoded.values() for recipient in recipients[:3]
        if recipient.get('player_id')
    }
    directory = {
        str(player['player_id']): {
            'player_id': str(player['player_id']),
            'name': _profile_name(player, {}, str(player['player_id'])),
            'avatar': player.get('avatar') or '',
        }
        for player in (Player.select().where(
            Player.player_id.in_(recipient_ids), Player.parent_player_id.is_null(True),
        ).dicts() if recipient_ids else [])
    }
    awards = []
    for row in rows:
        recipients = decoded[row.id]
        entries = []
        admin_recipients = []
        for position, recipient in enumerate(recipients[:3], start=1):
            player_id = str(recipient.get('player_id') or '')
            player = directory.get(player_id) or {
                'player_id': player_id, 'name': player_id, 'avatar': '',
            }
            reason = str(recipient.get('reason') or '').strip()
            admin_recipients.append({**player, 'reason': reason})
            entries.append({
                'position': position,
                **player,
                'value': position,
                'display_value': '评审入选',
                'evidence': reason,
                'tied': False,
            })
        awards.append({
            'id': row.id,
            'key': f'manual-{row.id}',
            'category': MANUAL_CATEGORY[0],
            'title': row.title,
            'description': row.description,
            'method': '由赛事管理员结合赛事实况评选，获奖理由随名单公开。',
            'is_manual': True,
            'status': 'ready',
            'entries': entries,
            'recipients': admin_recipients,
            'created_at': _iso(row.created_at),
            'updated_at': _iso(row.updated_at),
        })
    return awards


def _with_manual_awards(payload: dict[str, Any], cup: str) -> dict[str, Any]:
    manual = _manual_awards(cup)
    if manual:
        payload['categories'] = [
            *payload.get('categories', []),
            {'key': MANUAL_CATEGORY[0], 'label': MANUAL_CATEGORY[1]},
        ]
        payload['awards'] = [*payload.get('awards', []), *manual]
    payload['available_award_count'] = sum(
        award.get('status') == 'ready' for award in payload.get('awards', [])
    )
    return payload


def refresh_season_honours(cup: str, *, include_archived: bool = False) -> dict[str, Any]:
    """Force one durable automatic snapshot; archived snapshots stay immutable."""
    season = Season.get_by_cup(cup) or {}
    existing = SeasonHonourSnapshot.get_or_none(SeasonHonourSnapshot.cup_name == cup)
    if existing and season.get('status') == 'archived' and not include_archived:
        return _decode_json(existing.payload_json, {})
    with _snapshot_lock:
        payload = _calculate_season_honours(cup)
        snapshot = existing or SeasonHonourSnapshot(cup_name=cup)
        snapshot.payload_json = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
        snapshot.calculated_at = datetime.now()
        snapshot.save(force_insert=existing is None)
        return payload


def build_season_honours(cup: str) -> dict[str, Any]:
    """Read the persisted daily snapshot and cheaply merge curated awards."""
    snapshot = SeasonHonourSnapshot.get_or_none(SeasonHonourSnapshot.cup_name == cup)
    payload = _decode_json(snapshot.payload_json, {}) if snapshot else {}
    if not payload:
        payload = refresh_season_honours(cup)
    # JSON round-tripping prevents request-specific manual data mutating a cache object.
    payload = json.loads(json.dumps(payload, ensure_ascii=False))
    return _with_manual_awards(payload, cup)


def admin_honours_payload(cup: str) -> dict[str, Any]:
    season = Season.get_by_cup(cup)
    if not season:
        raise HonourValidationError('赛季不存在')
    snapshot = SeasonHonourSnapshot.get_or_none(SeasonHonourSnapshot.cup_name == cup)
    return {
        'cup': cup,
        'cup_alias': season.get('cup_alias') or season.get('name') or cup,
        'season_status': season.get('status') or 'active',
        'snapshot_calculated_at': _iso(snapshot.calculated_at) if snapshot else None,
        'players': _player_directory(cup),
        'awards': _manual_awards(cup),
    }


def save_manual_honour(cup: str, data: dict[str, Any], award_id: int | None = None) -> dict[str, Any]:
    if not Season.get_by_cup(cup):
        raise HonourValidationError('赛季不存在')
    title = str(data.get('title') or '').strip()
    description = str(data.get('description') or '').strip()
    if not title or len(title) > 120:
        raise HonourValidationError('奖项名称不能为空，且不能超过 120 个字符')
    if not description or len(description) > 1000:
        raise HonourValidationError('奖项说明不能为空，且不能超过 1000 个字符')
    recipients = data.get('recipients')
    if not isinstance(recipients, list) or not 1 <= len(recipients) <= 3:
        raise HonourValidationError('请选择 1–3 名获奖选手')
    valid_players = {item['player_id'] for item in _player_directory(cup)}
    normalized = []
    seen = set()
    for recipient in recipients:
        if not isinstance(recipient, dict):
            raise HonourValidationError('获奖选手格式无效')
        player_id = Player.canonical_player_id(str(recipient.get('player_id') or '').strip())
        reason = str(recipient.get('reason') or '').strip()
        if not player_id or player_id not in valid_players:
            raise HonourValidationError('获奖选手不在该赛季参赛名单中')
        if player_id in seen:
            raise HonourValidationError('同一名选手不能重复入选')
        if not reason or len(reason) > 500:
            raise HonourValidationError('每名选手都需要填写不超过 500 个字符的获奖理由')
        seen.add(player_id)
        normalized.append({'player_id': player_id, 'reason': reason})

    if award_id is None:
        row = ManualHonourAward.create(
            cup_name=cup, title=title, description=description,
            recipients_json=json.dumps(normalized, ensure_ascii=False),
        )
    else:
        row = ManualHonourAward.get_or_none(
            (ManualHonourAward.id == award_id) & (ManualHonourAward.cup_name == cup)
        )
        if row is None:
            raise HonourValidationError('手动奖项不存在')
        row.title = title
        row.description = description
        row.recipients_json = json.dumps(normalized, ensure_ascii=False)
        row.save()
    return next(award for award in _manual_awards(cup) if award['id'] == row.id)


def delete_manual_honour(cup: str, award_id: int) -> bool:
    return bool(ManualHonourAward.delete().where(
        (ManualHonourAward.id == award_id) & (ManualHonourAward.cup_name == cup)
    ).execute())
