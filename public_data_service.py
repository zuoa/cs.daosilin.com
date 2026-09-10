"""Shared payload builders for public APIs and search-friendly HTML."""

from datetime import datetime

from peewee import fn

from community_rating_service import community_rating_summaries
from database import (
    Config,
    CupDayChampion,
    DemoAnalysis,
    Match,
    MatchPlayer,
    Player,
    PlayerPerfectRankHistory,
    PlayerTitle,
    Season,
)
from demo_service import load_demo_context
from player_summary_service import get_public_summary
from portrait_service import portrait_payload
from title_service import title_service


def _iso_dt(value):
    if isinstance(value, datetime):
        return value.isoformat(timespec='seconds')
    return value


def season_list_payload():
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
    for season in seasons:
        Season.annotate(season)
        cup = season.get('cup_name')
        season['match_count'] = match_counts.get(cup, 0)
        season['day_count'] = day_counts.get(cup, 0)
        for key in ('created_at', 'updated_at', 'start_date', 'end_date'):
            value = season.get(key)
            if isinstance(value, datetime):
                season[key] = value.isoformat(timespec='seconds')
    seasons.sort(key=lambda item: (
        item.get('start_date') or '',
        item.get('cup_name') or '',
    ), reverse=True)
    return seasons


def build_cup_players(cup, day=None, *, include_scope=False):
    all_players = list(Player.select().where(Player.parent_player_id.is_null(True)).dicts())
    all_players_map = {player['player_id']: player for player in all_players}
    day_champion = CupDayChampion.get_champion_by_cup_and_day(cup, day)
    all_champions = CupDayChampion.filter_records(cup_name=cup)
    all_champions.sort(key=lambda champion: champion.get('day', ''))

    filter_params = {'cup_name': cup}
    if day is not None:
        filter_params['play_day'] = day
    players = MatchPlayer.filter_records(**filter_params)
    scope = {
        'match_count': len({
            str(player['match_id']) for player in players if player.get('match_id')
        }),
    }
    account_map = Player.account_map()
    players_map = {}
    champion_ids = {
        account_map.get(item, item)
        for item in (day_champion.get('champion_team_player_ids', '').split(',')
                     if day_champion else [])
        if item
    }
    runner_up_ids = {
        account_map.get(item, item)
        for item in (day_champion.get('runner_up_team_player_ids', '').split(',')
                     if day_champion else [])
        if item
    }
    for raw_player in players:
        player_id = account_map.get(str(raw_player['player_id']), str(raw_player['player_id']))
        profile = all_players_map.get(player_id, {})
        players_map[player_id] = {
            'nickname': profile.get('nickname') or raw_player['nickname'],
            'avatar': profile.get('avatar') or raw_player['avatar'],
            'player_id': player_id,
            'alias_name': profile.get('alias_name', ''),
            'live_url': profile.get('live_url') or '',
            'perfect_score': profile.get('perfect_score'),
            'perfect_level': profile.get('perfect_level'),
            'perfect_stars': profile.get('perfect_stars'),
            'perfect_rank_updated_at': _iso_dt(profile.get('perfect_rank_updated_at')),
            'team_name': raw_player.get('team_name', ''),
            'is_champion': player_id in champion_ids,
            'is_runner_up': player_id in runner_up_ids,
        }
    exploits = MatchPlayer.get_match_exploits(
        cup, players_map.keys(), day, identity_map=account_map,
    )
    stored_titles = (
        PlayerTitle.get_players_titles(players_map.keys(), cup, day)
        if not day else {}
    )

    player_data = []
    for player_id, player in players_map.items():
        data = exploits.get(str(player_id))
        if data:
            player.update(data)
        profile_avatar = all_players_map.get(player_id, {}).get('avatar')
        if profile_avatar:
            player['avatar'] = profile_avatar
        for champion in all_champions:
            champion_players = {
                account_map.get(item, item)
                for item in champion.get('champion_team_player_ids', '').split(',') if item
            }
            runner_up_players = {
                account_map.get(item, item)
                for item in champion.get('runner_up_team_player_ids', '').split(',') if item
            }
            if player_id in champion_players:
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('champion_team_name'),
                    'trophy': 'champion',
                })
            if player_id in runner_up_players:
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('runner_up_team_name'),
                    'trophy': 'runner_up',
                })
        player_data.append(player)

    cup_days = MatchPlayer.get_cup_day_set(cup)
    from baokemeng_service import draft_pick_summaries
    draft_stats = draft_pick_summaries([day] if day else cup_days, list(players_map))
    for player in player_data:
        player['draft_pick'] = draft_stats.get(str(player['player_id']))
    player_data.sort(key=lambda item: item.get('avg_pw_rating', 0), reverse=True)
    if day:
        comparable_players = [player for player in player_data if player.get('match_count')]
        for player in comparable_players:
            player['titles'] = title_service.build_title_rows(player, comparable_players)
    else:
        for player in player_data:
            player['titles'] = stored_titles.get(str(player['player_id']), [])
        community_ratings = community_rating_summaries(
            cup, [player['player_id'] for player in player_data],
        )
        for player in player_data:
            player['community_rating'] = community_ratings.get(str(player['player_id']))
    if include_scope:
        return player_data, cup_days, scope
    return player_data, cup_days


def player_detail_payload(player_id, cup, day=None):
    requested_player_id = player_id
    player_id = Player.canonical_player_id(player_id)
    record = Player.get_or_none(Player.player_id == player_id)
    if not record:
        return None, '选手不存在'
    player = record.to_dict()
    player.pop('parent_player_id', None)
    player['portrait'] = portrait_payload(record)
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
        return None, '该选手在此杯赛/日期下无数据'

    all_champions = CupDayChampion.filter_records(cup_name=cup)
    all_champions.sort(key=lambda champion: champion.get('day', ''))
    account_map = Player.account_map()
    trophy_history = []
    for champion in all_champions:
        champion_ids = {
            account_map.get(item, item)
            for item in champion.get('champion_team_player_ids', '').split(',') if item
        }
        runner_up_ids = {
            account_map.get(item, item)
            for item in champion.get('runner_up_team_player_ids', '').split(',') if item
        }
        if player_id in champion_ids:
            trophy_history.append({
                'day': champion.get('day'),
                'team_name': champion.get('champion_team_name'),
                'trophy': 'champion',
            })
        if player_id in runner_up_ids:
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

    all_player_profiles = list(
        Player.select().where(Player.parent_player_id.is_null(True)).dicts()
    )
    comparison_stats = MatchPlayer.get_match_exploits(
        cup, [profile['player_id'] for profile in all_player_profiles], day,
    )
    all_players_data = []
    for profile in all_player_profiles:
        data = comparison_stats.get(str(profile['player_id']))
        if data:
            data['player_id'] = profile['player_id']
            data['nickname'] = profile['nickname']
            all_players_data.append(data)
    comparison_player = next(
        (data for data in all_players_data if data['player_id'] == player_id), None,
    )
    if comparison_player:
        comparison_player['day_history'] = [item['data'] for item in historical_data]
        titles = title_service.build_title_rows(comparison_player, all_players_data)
    else:
        titles = []

    player_rankings = {}
    ranking_fields = (
        'avg_pw_rating', 'total_kills', 'kd_ratio', 'win_rate', 'avg_adpr', 'total_mvp',
    )
    for field in ranking_fields:
        if field in player_data:
            sorted_players = sorted(
                all_players_data, key=lambda item: item.get(field, 0), reverse=True,
            )
            try:
                player_rankings[field] = next(
                    index for index, item in enumerate(sorted_players, start=1)
                    if item['player_id'] == player_id
                )
            except StopIteration:
                player_rankings[field] = len(all_players_data)

    match_records = MatchPlayer.get_player_match_records(cup, player_id, day)
    analysis_by_match = {
        row.match_id: row
        for row in DemoAnalysis.select().where(
            DemoAnalysis.match_id.in_([match['match_id'] for match in match_records])
        )
    } if match_records else {}
    for match in match_records:
        match['start_time'] = _iso_dt(match.get('start_time'))
        match['end_time'] = _iso_dt(match.get('end_time'))
        match['mvp'] = bool(match.get('mvp'))
        analysis = analysis_by_match.get(match['match_id'])
        match['demo_analysis'] = ({
            'status': analysis.status,
            'metric_version': analysis.metric_version,
            'updated_at': _iso_dt(analysis.updated_at),
        } if analysis else {'status': 'pending'})

    return {
        'player': player,
        'canonical_player_id': player_id,
        'requested_player_id': requested_player_id,
        'perfect_rank_history': [{
            'score': sample['score'],
            'level': sample['level'],
            'stars': sample['stars'],
            'sampled_at': _iso_dt(sample['sampled_at']),
        } for sample in PlayerPerfectRankHistory.get_player_history(player_id)],
        'player_data': player_data,
        'titles': titles,
        'trophy_history': trophy_history,
        'historical_data': historical_data,
        'player_rankings': player_rankings,
        'map_stats': MatchPlayer.get_player_map_stats(cup, player_id, day),
        'match_records': match_records,
        'kill_matchups': MatchPlayer.get_player_kill_matchups(cup, player_id, day),
        'season_summary': get_public_summary(cup, player_id),
        'cup': cup,
        'cup_alias': Season.display_name(cup),
        'day': day,
        'cup_days': cup_days,
        'last_crawl_time': Config.get_value('last_crawl_time'),
    }, None
