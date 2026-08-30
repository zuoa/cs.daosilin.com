"""Credential, persistence and aggregation helpers for asynchronous demo analysis."""
import json
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

from config import (DEMO_CREDENTIAL_ENCRYPTION_KEY, DEMO_METRIC_VERSION,
                    WMPVP_ACCESS_TOKEN, WMPVP_STEAM_ID)
from database import (Config, DemoAnalysis, DemoCredential, DemoPlayerStats,
                      MatchPlayer, Player, fn)


PARSER_NAME = 'cs2-analyser-tool'
PARSER_VERSION = '88cb54ea0267fc8f4a8ae8d03987b50aec2a0653'


def demo_analysis_enabled():
    return str(Config.get_value('demo_analysis_enabled') or '').strip().lower() \
        in ('1', 'true', 'yes', 'on')


def set_demo_analysis_enabled(enabled: bool):
    Config.set_value('demo_analysis_enabled', '1' if enabled else '0')
    return bool(enabled)


def _fernet() -> Fernet:
    if not DEMO_CREDENTIAL_ENCRYPTION_KEY:
        raise ValueError('服务端未配置 DEMO_CREDENTIAL_ENCRYPTION_KEY，不能保存 Demo 凭证')
    try:
        return Fernet(DEMO_CREDENTIAL_ENCRYPTION_KEY.encode('ascii'))
    except (ValueError, TypeError) as exc:
        raise ValueError('DEMO_CREDENTIAL_ENCRYPTION_KEY 不是有效的 Fernet key') from exc


def save_demo_credential(steam_id: str, access_token: str) -> DemoCredential:
    steam_id = (steam_id or '').strip()
    access_token = (access_token or '').strip()
    if not steam_id.isdigit() or len(steam_id) < 15:
        raise ValueError('SteamID64 格式不正确')
    if len(access_token) < 16:
        raise ValueError('PWA access token 格式不正确')
    encrypted = _fernet().encrypt(access_token.encode()).decode()
    hint = '已加密保存'
    row, _ = DemoCredential.get_or_create(
        source='pwa',
        defaults={'steam_id': steam_id, 'encrypted_access_token': encrypted},
    )
    row.steam_id = steam_id
    row.encrypted_access_token = encrypted
    row.token_hint = hint
    row.last_error = None
    row.save()
    return row


def load_demo_credential():
    row = DemoCredential.get_or_none(DemoCredential.source == 'pwa')
    if not row:
        if WMPVP_ACCESS_TOKEN and WMPVP_STEAM_ID:
            return {'steam_id': WMPVP_STEAM_ID, 'access_token': WMPVP_ACCESS_TOKEN,
                    'source': 'wmpvp_default'}
        return None
    try:
        token = _fernet().decrypt(row.encrypted_access_token.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise ValueError('Demo 凭证无法解密，请在后台重新保存') from exc
    return {'steam_id': row.steam_id, 'access_token': token, 'source': 'database'}


def revoke_demo_credential() -> int:
    return DemoCredential.delete().where(DemoCredential.source == 'pwa').execute()


def demo_credential_status():
    row = DemoCredential.get_or_none(DemoCredential.source == 'pwa')
    fallback_configured = bool(WMPVP_ACCESS_TOKEN and WMPVP_STEAM_ID)
    return {
        'configured': bool(row) or fallback_configured,
        'database_configured': bool(row),
        'source': 'database' if row else 'wmpvp_default' if fallback_configured else 'none',
        'encryption_ready': bool(DEMO_CREDENTIAL_ENCRYPTION_KEY),
        'steam_id': row.steam_id if row else WMPVP_STEAM_ID if fallback_configured else '',
        'token_hint': row.token_hint if row else '复用现有采集凭证' if fallback_configured else '',
        'last_validated_at': row.last_validated_at.isoformat() if row and row.last_validated_at else None,
        'last_error': row.last_error if row else None,
    }


def has_demo_credential():
    return (DemoCredential.select().where(DemoCredential.source == 'pwa').exists()
            or bool(WMPVP_ACCESS_TOKEN and WMPVP_STEAM_ID))


def _side_count(value, key='total'):
    return int((value or {}).get(key) or 0)


def _side_rate_to_total(rate, rounds, side):
    return float((rate or {}).get(side) or 0) * int((rounds or {}).get(side) or 0) / 100.0


def persist_analysis(match_id: str, payload: dict) -> int:
    """Validate and atomically replace all player rows for a parsed match."""
    map_data = payload.get('map_data') or {}
    players = payload.get('players') or {}
    if isinstance(players, list):
        players = {str(p.get('steam_id')): p for p in players}
    total_rounds = int(map_data.get('total_rounds') or 0)
    if total_rounds <= 0 or len(players) < 2:
        raise ValueError('解析结果缺少有效回合或选手数据')

    platform_rows = list(MatchPlayer.select().where(MatchPlayer.match_id == match_id))
    player_ids = {str(row.player_id) for row in platform_rows}
    steam_to_player = {
        str(player.steam_id): str(player.player_id)
        for player in Player.select().where(Player.steam_id.is_null(False))
        if player.steam_id
    }
    player_to_steam = {player_id: steam_id for steam_id, player_id in steam_to_player.items()}
    parsed_ids = {str((p or {}).get('steam_id') or key) for key, p in players.items()}
    expected_steam_ids = {player_to_steam.get(pid, pid) for pid in player_ids}
    required = max(1, int(len(expected_steam_ids) * 0.8 + 0.999)) if expected_steam_ids else 1
    if len(parsed_ids & expected_steam_ids) < required:
        raise ValueError('Demo SteamID 与比赛阵容匹配不足 80%')

    rows = []
    for key, raw in players.items():
        raw = raw or {}
        steam_id = str(raw.get('steam_id') or key)
        player_id = steam_to_player.get(steam_id, steam_id)
        kills = raw.get('kill_stats') or {}
        assists = raw.get('assist_stats') or {}
        map_stats = raw.get('player_map_stats') or {}
        multi = map_stats.get('multi_kills') or {}
        opening = raw.get('opening_duel_stats') or {}
        side = raw.get('side_stats') or {}
        rounds = side.get('rounds') or {}
        side_adr = side.get('adr') or {}
        side_kast = side.get('kast') or {}
        utility = raw.get('utility_stats') or {}
        damage = utility.get('utility_damage') or {}
        grenades = utility.get('grenades_thrown') or {}
        rating = raw.get('rating') or {}
        rows.append({
            'match_id': match_id, 'player_id': player_id,
            'nickname': raw.get('name'), 'team_id': int(raw.get('team_id') or 0),
            'rounds_total': _side_count(rounds) or total_rounds,
            'rounds_ct': _side_count(rounds, 'ct'), 'rounds_t': _side_count(rounds, 't'),
            'kills': int(kills.get('total') or 0), 'deaths': int(raw.get('deaths') or 0),
            'assists': int(assists.get('total') or 0), 'headshots': int(kills.get('headshots') or 0),
            'team_kills': int(kills.get('team_kills') or 0),
            'damage_given': int(assists.get('damage_given') or 0),
            'kast_rounds': float(map_stats.get('kast') or 0) * total_rounds / 100.0,
            'mvps': int(map_stats.get('mvps') or 0), 'aces': int(map_stats.get('aces') or 0),
            'two_kill': int(multi.get('k2') or 0), 'three_kill': int(multi.get('k3') or 0),
            'four_kill': int(multi.get('k4') or 0), 'five_kill': int(multi.get('k5') or 0),
            'clutches_won': int(map_stats.get('clutches_won') or 0),
            'trade_kills': int(kills.get('trade_kills') or 0),
            'deaths_traded': _side_count(raw.get('deaths_traded')),
            'opening_kills': _side_count(opening.get('opening_kills')),
            'opening_deaths': _side_count(opening.get('opening_deaths')),
            'opening_round_wins': float(opening.get('opening_success_rate') or 0)
                                  * _side_count(opening.get('opening_kills')) / 100.0,
            'flash_assists': int(assists.get('flashed_enemies') or 0),
            'enemies_flashed': int(utility.get('enemies_flashed') or 0),
            'friends_flashed': int(utility.get('friends_flashed') or 0),
            'enemy_flash_seconds': float(utility.get('enemy_flash_time_seconds') or 0),
            'grenades_thrown': int(grenades.get('total') or 0),
            'flash_thrown': int(grenades.get('flash') or 0),
            'smoke_thrown': int(grenades.get('smoke') or 0), 'he_thrown': int(grenades.get('he') or 0),
            'molotov_thrown': int(grenades.get('molotov') or 0),
            'incendiary_thrown': int(grenades.get('incendiary') or 0),
            'decoy_thrown': int(grenades.get('decoy') or 0),
            'utility_damage': int(damage.get('total') or 0), 'he_damage': int(damage.get('he') or 0),
            'fire_damage': int(damage.get('fire') or 0),
            'unused_utility_value': int(utility.get('unused_utility_value') or 0),
            'ct_kills': _side_count(side.get('kills'), 'ct'), 't_kills': _side_count(side.get('kills'), 't'),
            'ct_deaths': _side_count(side.get('deaths'), 'ct'), 't_deaths': _side_count(side.get('deaths'), 't'),
            'ct_damage': _side_rate_to_total(side_adr, rounds, 'ct'),
            't_damage': _side_rate_to_total(side_adr, rounds, 't'),
            'ct_kast_rounds': _side_rate_to_total(side_kast, rounds, 'ct'),
            't_kast_rounds': _side_rate_to_total(side_kast, rounds, 't'),
            'demo_rating': float(rating.get('value') or 0),
            'rating_kills': float(rating.get('kills') or 0), 'rating_damage': float(rating.get('damage') or 0),
            'rating_survival': float(rating.get('survival') or 0), 'rating_kast': float(rating.get('kast') or 0),
            'rating_multi_kill': float(rating.get('multi_kill') or 0),
            'rating_round_swing': float(rating.get('round_swing') or 0),
            'approx_ekast_percent': float(map_stats.get('approx_ekast_percent') or 0),
            'approx_round_swing_percent': float(map_stats.get('approx_round_swing_percent') or 0),
            'weapon_kills': json.dumps(kills.get('weapons_kills') or {}, ensure_ascii=False),
            'raw_stats': json.dumps(raw, ensure_ascii=False),
        })
    with DemoPlayerStats._meta.database.atomic():
        DemoPlayerStats.delete().where(DemoPlayerStats.match_id == match_id).execute()
        if rows:
            DemoPlayerStats.insert_many(rows).execute()
    return len(rows)


def get_demo_player_stats(cup_name, player_id: str, play_day: str = None):
    """Aggregate completed-demo metrics; missing demos are excluded, never zero-filled."""
    query = (DemoPlayerStats
             .select(DemoPlayerStats, MatchPlayer.cup_name, MatchPlayer.play_day)
             .join(MatchPlayer, on=(
                 (DemoPlayerStats.match_id == MatchPlayer.match_id) &
                 (DemoPlayerStats.player_id == MatchPlayer.player_id)
             ))
             .join(DemoAnalysis, on=(DemoAnalysis.match_id == DemoPlayerStats.match_id))
             .where(DemoPlayerStats.player_id == player_id,
                    DemoAnalysis.status == 'completed',
                    DemoAnalysis.metric_version == DEMO_METRIC_VERSION))
    platform = MatchPlayer.select(fn.COUNT(fn.DISTINCT(MatchPlayer.match_id))).where(
        MatchPlayer.player_id == player_id)
    cup_names = cup_name if isinstance(cup_name, (list, tuple, set)) else None
    if cup_names:
        query = query.where(MatchPlayer.cup_name.in_(list(cup_names)))
        platform = platform.where(MatchPlayer.cup_name.in_(list(cup_names)))
    elif cup_name:
        query = query.where(MatchPlayer.cup_name == cup_name)
        platform = platform.where(MatchPlayer.cup_name == cup_name)
    if play_day:
        query = query.where(MatchPlayer.play_day == play_day)
        platform = platform.where(MatchPlayer.play_day == play_day)
    rows = list(query)
    total_matches = int(platform.scalar() or 0)
    scope = MatchPlayer.select(MatchPlayer.match_id).where(MatchPlayer.player_id == player_id)
    if cup_names:
        scope = scope.where(MatchPlayer.cup_name.in_(list(cup_names)))
    elif cup_name:
        scope = scope.where(MatchPlayer.cup_name == cup_name)
    if play_day:
        scope = scope.where(MatchPlayer.play_day == play_day)
    scoped_ids = [row.match_id for row in scope]
    status_counts = {}
    if scoped_ids:
        for analysis in DemoAnalysis.select().where(DemoAnalysis.match_id.in_(scoped_ids)):
            status_counts[analysis.status] = status_counts.get(analysis.status, 0) + 1
    if not rows:
        return {'coverage': {'completed': 0, 'total': total_matches, 'ratio': 0.0},
                'metrics': None, 'effective_core': None, 'status_counts': status_counts}

    def total(field):
        return sum(float(getattr(row, field) or 0) for row in rows)
    rounds = total('rounds_total')
    kills = total('kills')
    deaths = total('deaths')
    opening = total('opening_kills') + total('opening_deaths')
    flash_events = total('enemies_flashed') + total('friends_flashed')
    completed = len({row.match_id for row in rows})
    ratio = lambda n, d: round(n / d, 4) if d else 0.0
    metrics = {
        'match_count': completed, 'total_rounds': int(rounds),
        'total_kills': int(kills), 'total_deaths': int(deaths), 'total_assists': int(total('assists')),
        'total_headshots': int(total('headshots')), 'total_damage': int(total('damage_given')),
        'avg_adpr': ratio(total('damage_given'), rounds), 'kast_ratio': ratio(total('kast_rounds'), rounds),
        'avg_kast': ratio(total('kast_rounds'), rounds), 'headshot_ratio': ratio(total('headshots'), kills),
        'total_trade_frags': int(total('trade_kills')), 'total_deaths_traded': int(total('deaths_traded')),
        'trade_kill_share': ratio(total('trade_kills'), kills),
        'death_trade_rate': ratio(total('deaths_traded'), deaths),
        'total_first_kills': int(total('opening_kills')), 'total_first_deaths': int(total('opening_deaths')),
        'opening_duel_win_rate': ratio(total('opening_kills'), opening),
        'opening_round_conversion': ratio(total('opening_round_wins'), total('opening_kills')),
        'total_2k': int(total('two_kill')), 'total_3k': int(total('three_kill')),
        'total_4k': int(total('four_kill')), 'total_5k': int(total('five_kill')),
        'total_aces': int(total('aces')), 'total_clutches_won': int(total('clutches_won')),
        'total_mvp': int(total('mvps')), 'total_team_kills': int(total('team_kills')),
        'flash_assists': int(total('flash_assists')), 'enemies_flashed': int(total('enemies_flashed')),
        'friends_flashed': int(total('friends_flashed')),
        'enemy_flash_seconds': round(total('enemy_flash_seconds'), 2),
        'average_enemy_flash_seconds': ratio(total('enemy_flash_seconds'), total('enemies_flashed')),
        'enemies_per_flash': ratio(total('enemies_flashed'), total('flash_thrown')),
        'team_flash_share': ratio(total('friends_flashed'), flash_events),
        'grenades_thrown': int(total('grenades_thrown')), 'flash_thrown': int(total('flash_thrown')),
        'smoke_thrown': int(total('smoke_thrown')), 'he_thrown': int(total('he_thrown')),
        'molotov_thrown': int(total('molotov_thrown')), 'incendiary_thrown': int(total('incendiary_thrown')),
        'decoy_thrown': int(total('decoy_thrown')), 'total_utility_damage': int(total('utility_damage')),
        'he_damage': int(total('he_damage')), 'fire_damage': int(total('fire_damage')),
        'utility_damage_per_round': ratio(total('utility_damage'), rounds),
        'utility_damage_per_throw': ratio(total('utility_damage'), total('grenades_thrown')),
        'unused_utility_value': int(total('unused_utility_value')),
        'ct_rounds': int(total('rounds_ct')), 't_rounds': int(total('rounds_t')),
        'ct_kills': int(total('ct_kills')), 't_kills': int(total('t_kills')),
        'ct_deaths': int(total('ct_deaths')), 't_deaths': int(total('t_deaths')),
        'ct_adr': ratio(total('ct_damage'), total('rounds_ct')), 't_adr': ratio(total('t_damage'), total('rounds_t')),
        'ct_kast': ratio(total('ct_kast_rounds'), total('rounds_ct')),
        't_kast': ratio(total('t_kast_rounds'), total('rounds_t')),
        'demo_rating': ratio(sum(row.demo_rating * row.rounds_total for row in rows), rounds),
        'rating_kills': ratio(sum(row.rating_kills * row.rounds_total for row in rows), rounds),
        'rating_damage': ratio(sum(row.rating_damage * row.rounds_total for row in rows), rounds),
        'rating_survival': ratio(sum(row.rating_survival * row.rounds_total for row in rows), rounds),
        'rating_kast': ratio(sum(row.rating_kast * row.rounds_total for row in rows), rounds),
        'rating_multi_kill': ratio(sum(row.rating_multi_kill * row.rounds_total for row in rows), rounds),
        'rating_round_swing': ratio(sum(row.rating_round_swing * row.rounds_total for row in rows), rounds),
        'metric_version': DEMO_METRIC_VERSION, 'source': 'demo',
    }
    weapon_kills = {}
    for row in rows:
        for weapon, count in json.loads(row.weapon_kills or '{}').items():
            weapon_kills[weapon] = weapon_kills.get(weapon, 0) + int(count or 0)
    metrics['weapon_kills'] = dict(sorted(weapon_kills.items(), key=lambda item: item[1], reverse=True))

    # Core metrics are mixed per match: completed demos are canonical, while
    # uncovered matches retain their platform row. Demo-only measurements
    # above intentionally keep the completed-demo denominator.
    completed_ids = {row.match_id for row in rows}
    fallback = MatchPlayer.select().where(MatchPlayer.player_id == player_id)
    if cup_names:
        fallback = fallback.where(MatchPlayer.cup_name.in_(list(cup_names)))
    elif cup_name:
        fallback = fallback.where(MatchPlayer.cup_name == cup_name)
    if play_day:
        fallback = fallback.where(MatchPlayer.play_day == play_day)
    if completed_ids:
        fallback = fallback.where(~(MatchPlayer.match_id.in_(completed_ids)))
    fallback = list(fallback)
    fsum = lambda field: sum(float(getattr(row, field) or 0) for row in fallback)
    core = {
        'total_kills': int(total('kills') + fsum('kill')),
        'total_deaths': int(total('deaths') + fsum('death')),
        'total_assists': int(total('assists') + fsum('assist')),
        'total_headshots': int(total('headshots') + fsum('headshot')),
        'total_health_damage': int(total('damage_given') + fsum('dmg_health')),
        'total_game_count': int(rounds + fsum('game_count')),
        'total_kast_rounds': total('kast_rounds') + fsum('kast'),
        'total_first_kills': int(total('opening_kills') + fsum('entry_kill')),
        'total_first_deaths': int(total('opening_deaths') + fsum('first_death')),
        'total_2k': int(total('two_kill') + fsum('two_kill')),
        'total_3k': int(total('three_kill') + fsum('three_kill')),
        'total_4k': int(total('four_kill') + fsum('four_kill')),
        'total_5k': int(total('five_kill') + fsum('five_kill')),
        'total_trade_frags': int(total('trade_kills') + fsum('trade_frag_count')),
        'total_grenade_damage': int(total('he_damage') + fsum('grenade_damage')),
        'total_inferno_damage': int(total('fire_damage') + fsum('inferno_damage')),
        'total_mvp': int(total('mvps') + fsum('mvp_value')),
    }
    core_rounds = core['total_game_count']
    core_opening = core['total_first_kills'] + core['total_first_deaths']
    core_multi = sum(core[key] for key in ('total_2k', 'total_3k', 'total_4k', 'total_5k'))
    core_utility = core['total_grenade_damage'] + core['total_inferno_damage']
    core.update({
        'total_rounds': core_rounds,
        'kd_ratio': ratio(core['total_kills'], core['total_deaths']),
        'avg_adpr': ratio(core['total_health_damage'], core_rounds),
        'avg_kast': ratio(core['total_kast_rounds'], core_rounds),
        'kast_ratio': ratio(core['total_kast_rounds'], core_rounds),
        'avg_headshot_ratio': ratio(core['total_headshots'], core['total_kills']),
        'headshot_ratio': ratio(core['total_headshots'], core['total_kills']),
        'kills_per_round': ratio(core['total_kills'], core_rounds),
        'deaths_per_round': ratio(core['total_deaths'], core_rounds),
        'assists_per_round': ratio(core['total_assists'], core_rounds),
        'opening_duel_win_rate': ratio(core['total_first_kills'], core_opening),
        'opening_duels_per_round': ratio(core_opening, core_rounds),
        'trade_kill_share': ratio(core['total_trade_frags'], core['total_kills']),
        'multi_kill_rounds': core_multi,
        'multi_kill_round_rate': ratio(core_multi, core_rounds),
        'total_utility_damage': core_utility,
        'utility_damage_per_round': ratio(core_utility, core_rounds),
    })
    return {
        'coverage': {'completed': completed, 'total': total_matches,
                     'ratio': ratio(completed, total_matches)},
        'metrics': metrics,
        'effective_core': core,
        'status_counts': status_counts,
    }


def attach_demo_stats(platform_data, cup_name, player_id, play_day=None):
    """Namespace sources and expose demo values as effective when available."""
    if not platform_data:
        return platform_data
    demo = get_demo_player_stats(cup_name, player_id, play_day)
    effective = dict(platform_data)
    if demo['metrics']:
        effective.update(demo['effective_core'] or {})
        demo_only = (
            'total_deaths_traded', 'death_trade_rate', 'opening_round_conversion',
            'total_aces', 'total_clutches_won', 'total_team_kills', 'flash_assists',
            'enemies_flashed', 'friends_flashed', 'enemy_flash_seconds',
            'average_enemy_flash_seconds', 'enemies_per_flash', 'team_flash_share',
            'grenades_thrown',
            'flash_thrown', 'smoke_thrown', 'he_thrown', 'molotov_thrown',
            'incendiary_thrown', 'decoy_thrown', 'utility_damage_per_throw',
            'unused_utility_value', 'ct_rounds', 't_rounds', 'ct_kills', 't_kills',
            'ct_deaths', 't_deaths', 'ct_adr', 't_adr', 'ct_kast', 't_kast',
            'demo_rating', 'rating_kills', 'rating_damage', 'rating_survival',
            'rating_kast', 'rating_multi_kill', 'rating_round_swing', 'weapon_kills',
        )
        effective.update({key: demo['metrics'][key] for key in demo_only
                          if key in demo['metrics']})
    effective['platform_data'] = dict(platform_data)
    effective['demo_data'] = demo['metrics']
    effective['demo_coverage'] = demo['coverage']
    completed = demo['coverage']['completed']
    total_matches = demo['coverage']['total']
    effective['metric_source'] = ('demo' if completed and completed == total_matches
                                  else 'mixed' if completed else 'platform')
    statuses = demo.get('status_counts') or {}
    active = any(statuses.get(name) for name in ('queued', 'downloading', 'validating', 'parsing'))
    if completed and completed == total_matches:
        analysis_status = 'completed'
    elif active:
        analysis_status = 'processing'
    elif completed:
        analysis_status = 'partial'
    elif statuses.get('blocked_credentials'):
        analysis_status = 'blocked_credentials'
    elif statuses.get('failed'):
        analysis_status = 'failed'
    elif statuses.get('unavailable') == total_matches and total_matches:
        analysis_status = 'unavailable'
    else:
        analysis_status = 'pending'
    effective['demo_analysis'] = {
        'status': analysis_status,
        'status_counts': statuses,
        'parser': PARSER_NAME,
        'parser_version': PARSER_VERSION,
        'metric_version': DEMO_METRIC_VERSION,
        'rating_experimental': True,
    }
    return effective
