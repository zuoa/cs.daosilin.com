"""Build, validate and aggregate DeepSeek season all-star ballots."""
from __future__ import annotations

import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any

from openai import OpenAI
from peewee import fn

from config import (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME,
                    LLM_REQUEST_TIMEOUT, SEASON_LINEUP_BALLOTS,
                    SEASON_LINEUP_PROMPT_VERSION)
from database import (CupDayChampion, Match, MatchPlayer, Player, Season,
                      SeasonLineupRun)


WEAPON_ROLES = ('awper', 'rifler')
FUNCTION_ROLES = ('opener', 'support', 'closer', 'flex')
REQUIRED_FUNCTIONS = {'opener', 'support', 'closer'}
REQUIRED_FUNCTION_ORDER = ('opener', 'support', 'closer')
PERSPECTIVES = ('individual', 'winning', 'fit')
PERSPECTIVE_LABELS = {
    'individual': '个人输出、样本可靠性与高阶影响',
    'winning': '胜率、冠亚军成果与团队成功背景',
    'fit': '主狙/步枪结构与突破、支援、残局互补',
}


class LineupValidationError(ValueError):
    pass


def llm_configured() -> bool:
    return bool(LLM_API_KEY and LLM_BASE_URL and LLM_MODEL_NAME)


def _number(value: Any, digits: int = 4) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    if number.is_integer():
        return int(number)
    return round(number, digits)


def _ratio(numerator: Any, denominator: Any) -> float | None:
    try:
        denominator = float(denominator)
        return round(float(numerator or 0) / denominator, 4) if denominator > 0 else None
    except (TypeError, ValueError):
        return None


def _optional_metric(value: Any, *, trusted_zero: bool = False) -> float | int | None:
    number = _number(value)
    return number if trusted_zero or number not in (None, 0) else None


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    if len(values) == 1:
        return {next(iter(values)): 0.5}
    result = {}
    for player_id, value in values.items():
        lower = sum(candidate < value for candidate in values.values())
        equal = sum(candidate == value for candidate in values.values())
        result[player_id] = round((lower + (equal - 1) / 2) / (len(values) - 1), 4)
    return result


def _average_present(*values: Any) -> float:
    present = [float(value) for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else 0.0


def _profile_name(profile: dict[str, Any], fallback: dict[str, Any], player_id: str) -> str:
    return str(profile.get('alias_name') or profile.get('nickname')
               or fallback.get('nickname') or player_id)


def _latest_data_cutoff(cup: str) -> str | None:
    value = (Match.select(fn.MAX(Match.end_time))
             .where(Match.cup_name == cup).scalar())
    return value.isoformat(timespec='seconds') if value else None


def _outcome_counts(cup: str, account_map: dict[str, str]) -> dict[str, dict[str, int]]:
    result = defaultdict(lambda: {'champion_count': 0, 'runner_up_count': 0})
    for row in CupDayChampion.filter_records(cup_name=cup):
        for key, field in (('champion_count', 'champion_team_player_ids'),
                           ('runner_up_count', 'runner_up_team_player_ids')):
            for raw_id in str(row.get(field) or '').split(','):
                if raw_id:
                    result[account_map.get(raw_id, raw_id)][key] += 1
    return result


def _metric_percentiles(candidates: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = {
        row['player_id']: float(row['metrics'][key])
        for row in candidates if row['metrics'].get(key) is not None
    }
    return _percentiles(values)


def build_selection_snapshot(cup: str) -> dict[str, Any]:
    """Freeze eligible candidates and evidence-backed role affinities."""
    season = Season.get_by_cup(cup)
    if not season:
        raise LineupValidationError('赛季不存在')
    account_map = Player.account_map()
    raw_rows = MatchPlayer.filter_records(cup_name=cup)
    fallback = {}
    player_ids = []
    for row in raw_rows:
        raw_id = str(row.get('player_id') or '')
        player_id = account_map.get(raw_id, raw_id)
        if player_id and player_id not in fallback:
            fallback[player_id] = row
            player_ids.append(player_id)
    aggregates = MatchPlayer.get_match_exploits(
        cup, player_ids, identity_map=account_map,
    ) if player_ids else {}
    maximum_matches = max(
        (int(row.get('match_count') or 0) for row in aggregates.values()), default=0,
    )
    minimum_matches = max(3, math.ceil(maximum_matches * 0.5)) if maximum_matches else 3
    eligible_ids = [
        player_id for player_id in player_ids
        if int((aggregates.get(player_id) or {}).get('match_count') or 0) >= minimum_matches
    ]
    profiles = {
        str(row['player_id']): row for row in
        (Player.select().where(
            Player.player_id.in_(eligible_ids), Player.parent_player_id.is_null(True),
        ).dicts() if eligible_ids else [])
    }
    outcomes = _outcome_counts(cup, account_map)
    candidates = []
    for player_id in eligible_ids:
        stats = aggregates[player_id]
        rounds = int(stats.get('total_rounds') or 0)
        demo = stats.get('demo_data') or {}
        coverage = stats.get('demo_coverage') or {}
        has_demo = int(coverage.get('completed') or 0) > 0
        clutch_total = demo.get('total_clutches_won')
        if clutch_total is None:
            clutch_total = sum(int(stats.get(key) or 0) for key in (
                'total_1v1', 'total_1v2', 'total_1v3', 'total_1v4', 'total_1v5'))
        metrics = {
            'match_count': int(stats.get('match_count') or 0),
            'round_count': rounds,
            'pwr_rating': _number(stats.get('avg_pw_rating')),
            'kd_ratio': _number(stats.get('kd_ratio')),
            'win_rate': _number(stats.get('win_rate')),
            'adr': _number(stats.get('avg_adpr')),
            'kast': _number(stats.get('avg_kast')),
            'kills_per_round': _number(stats.get('kills_per_round')),
            'deaths_per_round': _number(stats.get('deaths_per_round')),
            'opening_duels_per_round': _number(stats.get('opening_duels_per_round')),
            'opening_win_rate': _number(stats.get('opening_duel_win_rate')),
            'first_kills_per_round': _ratio(stats.get('total_first_kills'), rounds),
            'sniper_kills_per_round': _optional_metric(_ratio(stats.get('total_snipe_num'), rounds)),
            'sniper_kill_share': _optional_metric(_ratio(stats.get('total_snipe_num'), stats.get('total_kills'))),
            'trade_kill_share': _optional_metric(stats.get('trade_kill_share'), trusted_zero=has_demo),
            'utility_damage_per_round': _optional_metric(stats.get('utility_damage_per_round'), trusted_zero=has_demo),
            'multi_kill_round_rate': _number(stats.get('multi_kill_round_rate')),
            'mvp_match_rate': _number(stats.get('mvp_match_rate')),
            'clutches_per_match': _optional_metric(
                _ratio(clutch_total, coverage.get('completed') or stats.get('match_count')),
                trusted_zero=has_demo,
            ),
            'flash_assists_per_round': _optional_metric(
                _ratio(demo.get('flash_assists'), demo.get('total_rounds')),
                trusted_zero=has_demo,
            ),
            'enemies_flashed_per_round': _optional_metric(
                _ratio(demo.get('enemies_flashed'), demo.get('total_rounds')),
                trusted_zero=has_demo,
            ),
            'round_swing': _optional_metric(
                demo.get('approx_round_swing_percent'), trusted_zero=has_demo,
            ),
            **outcomes[player_id],
        }
        profile = profiles.get(player_id, {})
        candidates.append({
            'player_id': player_id,
            'player_name': _profile_name(profile, fallback.get(player_id, {}), player_id),
            'avatar': profile.get('avatar') or fallback.get(player_id, {}).get('avatar') or '',
            'metrics': metrics,
            'demo_coverage': {
                'completed': int(coverage.get('completed') or 0),
                'total': int(coverage.get('total') or stats.get('match_count') or 0),
                'ratio': _number(coverage.get('ratio')) or 0,
            },
        })

    metric_percentiles = {
        key: _metric_percentiles(candidates, key) for key in (
            'pwr_rating', 'win_rate', 'kills_per_round', 'opening_duels_per_round',
            'opening_win_rate', 'first_kills_per_round', 'sniper_kills_per_round',
            'sniper_kill_share', 'trade_kill_share', 'utility_damage_per_round',
            'flash_assists_per_round', 'enemies_flashed_per_round',
            'clutches_per_match', 'round_swing',
        )
    }
    death_values = {
        row['player_id']: -float(row['metrics']['deaths_per_round'])
        for row in candidates if row['metrics'].get('deaths_per_round') is not None
    }
    survival_percentiles = _percentiles(death_values)
    for row in candidates:
        player_id = row['player_id']
        affinity = {
            'awper': _average_present(
                metric_percentiles['sniper_kills_per_round'].get(player_id),
                metric_percentiles['sniper_kill_share'].get(player_id)),
            'opener': _average_present(
                metric_percentiles['opening_duels_per_round'].get(player_id),
                metric_percentiles['opening_win_rate'].get(player_id),
                metric_percentiles['first_kills_per_round'].get(player_id)),
            'support': _average_present(
                metric_percentiles['trade_kill_share'].get(player_id),
                metric_percentiles['utility_damage_per_round'].get(player_id),
                metric_percentiles['flash_assists_per_round'].get(player_id),
                metric_percentiles['enemies_flashed_per_round'].get(player_id)),
            'closer': _average_present(
                metric_percentiles['clutches_per_match'].get(player_id),
                metric_percentiles['round_swing'].get(player_id),
                survival_percentiles.get(player_id)),
        }
        sniper_evidence = float(row['metrics'].get('sniper_kills_per_round') or 0) > 0
        row['role_affinity'] = affinity
        row['allowed_weapon_roles'] = [
            *(['awper'] if sniper_evidence and affinity['awper'] >= 0.5 else []),
            'rifler',
        ]
        row['allowed_function_roles'] = [
            role for role in REQUIRED_FUNCTION_ORDER if affinity[role] >= 0.5
        ] + ['flex']
        row['rank_percentiles'] = {
            key: values[player_id] for key, values in metric_percentiles.items()
            if player_id in values
        }

    candidates.sort(key=lambda row: (
        -float(row['metrics'].get('pwr_rating') or 0), row['player_id'],
    ))
    snapshot = {
        'season': {
            'cup_name': cup,
            'name': season.get('cup_alias') or season.get('name') or cup,
            'data_cutoff': _latest_data_cutoff(cup),
        },
        'eligibility': {
            'minimum_matches': minimum_matches,
            'maximum_matches': maximum_matches,
            'candidate_count': len(candidates),
        },
        'candidates': candidates,
    }
    _ensure_snapshot_feasible(snapshot)
    return snapshot


def _ensure_snapshot_feasible(snapshot: dict[str, Any]) -> None:
    candidates = snapshot.get('candidates') or []
    if len(candidates) < 10:
        raise LineupValidationError(
            f'符合出勤门槛的选手仅 {len(candidates)} 人，至少需要 10 人')
    awpers = sum('awper' in row['allowed_weapon_roles'] for row in candidates)
    if awpers < 2:
        raise LineupValidationError('缺少两名有数据支持的主狙候选人')
    for role in REQUIRED_FUNCTION_ORDER:
        count = sum(role in row['allowed_function_roles'] for row in candidates)
        if count < 2:
            raise LineupValidationError(f'缺少两名可胜任 {role} 的候选人')
    bits = {'opener': 1, 'support': 2, 'closer': 4, 'flex': 0}
    states = {(0, 0, 0, 0, 0, 0)}
    for row in candidates:
        next_states = set(states)
        for fc, sc, fa, sa, fm, sm in states:
            for team in ('first', 'second'):
                if (team == 'first' and fc >= 5) or (team == 'second' and sc >= 5):
                    continue
                for weapon in row['allowed_weapon_roles']:
                    awp = int(weapon == 'awper')
                    if (team == 'first' and fa + awp > 1) or (team == 'second' and sa + awp > 1):
                        continue
                    for function in row['allowed_function_roles']:
                        bit = bits[function]
                        next_states.add(
                            (fc + 1, sc, fa + awp, sa, fm | bit, sm)
                            if team == 'first'
                            else (fc, sc + 1, fa, sa + awp, fm, sm | bit)
                        )
        states = next_states
    if (5, 5, 1, 1, 7, 7) not in states:
        raise LineupValidationError('候选人角色重叠，无法组成两套不重复的完整阵容')


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    prompt_input = json.loads(json.dumps(snapshot, ensure_ascii=False))
    for candidate in prompt_input.get('candidates', []):
        candidate.pop('avatar', None)
    body = {
        'prompt_version': SEASON_LINEUP_PROMPT_VERSION,
        'model': LLM_MODEL_NAME,
        'ballots': SEASON_LINEUP_BALLOTS,
        'input': prompt_input,
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


SYSTEM_PROMPT = """你是 CS2 赛季荣誉评审团成员。你要在候选人中选出最佳一阵和二阵。
只能使用输入 JSON 的数据；null 表示未知，不得当作 0，不得虚构比赛事件、沟通、IGL、地图站位或角色。
评选价值取向固定为：个人数据影响 50%，胜率、冠亚军与团队成功 50%。样本量和 Demo 覆盖率是置信度，不是奖励项。
一阵、二阵各 5 人，10 人不得重复。每阵必须恰好 1 名 awper 和 4 名 rifler，并至少各有 1 名 opener、support、closer。
每人的 weapon_role 和 function_role 只能从其 allowed_* 列表选择。reason 用 18-70 个汉字概括入选原因；evidence 列出 1-5 个输入 metrics 中真实存在的 key。
只输出 JSON 对象，顶层必须恰好包含 first_team 和 second_team，两者都是 5 个对象的数组。
每个对象必须恰好包含 player_id、weapon_role、function_role、reason、evidence。
""".strip()


def _ballot_prompt(snapshot: dict[str, Any], perspective: str,
                   ballot_index: int) -> str:
    candidates = json.loads(json.dumps(snapshot['candidates'], ensure_ascii=False))
    for candidate in candidates:
        candidate.pop('avatar', None)
    random.SystemRandom().shuffle(candidates)
    payload = {
        'season': snapshot['season'],
        'eligibility': snapshot['eligibility'],
        'review_focus': PERSPECTIVE_LABELS[perspective],
        'ballot_index': ballot_index,
        'candidates': candidates,
    }
    return ('请独立完成本轮选票。评审侧重是交叉检查视角，不改变 50/50 '
            '总权重。输入：\n' +
            json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _validate_member(value: Any, candidates: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise LineupValidationError('阵容成员必须是对象')
    if set(value) != {'player_id', 'weapon_role', 'function_role', 'reason', 'evidence'}:
        raise LineupValidationError('阵容成员字段不合规')
    player_id = str(value.get('player_id') or '')
    candidate = candidates.get(player_id)
    if not candidate:
        raise LineupValidationError('选票包含非候选人')
    weapon = str(value.get('weapon_role') or '')
    function = str(value.get('function_role') or '')
    if weapon not in candidate['allowed_weapon_roles']:
        raise LineupValidationError('武器角色没有数据支持')
    if function not in candidate['allowed_function_roles']:
        raise LineupValidationError('战术功能没有数据支持')
    reason = re.sub(r'\s+', ' ', str(value.get('reason') or '')).strip()
    if not 18 <= len(reason) <= 70:
        raise LineupValidationError('入选理由长度不合规')
    evidence = value.get('evidence')
    if not isinstance(evidence, list) or not 1 <= len(evidence) <= 5:
        raise LineupValidationError('证据字段不合规')
    metric_keys = set(candidate['metrics'])
    evidence = list(dict.fromkeys(str(key) for key in evidence))
    if any(key not in metric_keys or candidate['metrics'].get(key) is None for key in evidence):
        raise LineupValidationError('选票引用了缺失指标')
    return {
        'player_id': player_id,
        'weapon_role': weapon,
        'function_role': function,
        'reason': reason,
        'evidence': evidence,
    }


def validate_ballot(raw: str | dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        raise LineupValidationError('DeepSeek 返回的不是有效 JSON') from exc
    if not isinstance(value, dict) or set(value) != {'first_team', 'second_team'}:
        raise LineupValidationError('选票顶层结构不合规')
    candidates = {row['player_id']: row for row in snapshot['candidates']}
    result = {}
    seen = set()
    for team_key in ('first_team', 'second_team'):
        team = value.get(team_key)
        if not isinstance(team, list) or len(team) != 5:
            raise LineupValidationError('每套阵容必须恰好 5 人')
        normalized = [_validate_member(member, candidates) for member in team]
        ids = [member['player_id'] for member in normalized]
        if len(set(ids)) != 5 or seen.intersection(ids):
            raise LineupValidationError('一阵二阵不得出现重复选手')
        if sum(member['weapon_role'] == 'awper' for member in normalized) != 1:
            raise LineupValidationError('每套阵容必须恰好一名主狙')
        functions = {member['function_role'] for member in normalized}
        if not REQUIRED_FUNCTIONS.issubset(functions):
            raise LineupValidationError('阵容未覆盖突破、支援和残局')
        seen.update(ids)
        result[team_key] = normalized
    return result


def generate_ballot(snapshot: dict[str, Any], perspective: str, ballot_index: int,
                    client: OpenAI | None = None) -> tuple[dict[str, Any], dict[str, int | None]]:
    if not llm_configured():
        raise LineupValidationError('LLM_API_KEY 未配置')
    client = client or OpenAI(
        api_key=LLM_API_KEY, base_url=LLM_BASE_URL,
        timeout=LLM_REQUEST_TIMEOUT, max_retries=0,
    )
    response = client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': _ballot_prompt(snapshot, perspective, ballot_index)},
        ],
        response_format={'type': 'json_object'},
        max_tokens=2200,
        temperature=0.7,
        stream=False,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    content = response.choices[0].message.content if response.choices else ''
    ballot = validate_ballot(content, snapshot)
    ballot['perspective'] = perspective
    ballot['ballot_index'] = ballot_index
    usage = getattr(response, 'usage', None)
    return ballot, {
        'prompt_tokens': getattr(usage, 'prompt_tokens', None),
        'completion_tokens': getattr(usage, 'completion_tokens', None),
        'total_tokens': getattr(usage, 'total_tokens', None),
    }


def _add_score(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(a + b for a, b in zip(left, right))


def _prefer(candidate, current) -> bool:
    if current is None or candidate[0] > current[0]:
        return True
    if candidate[0] < current[0]:
        return False
    return tuple(candidate[1]) < tuple(current[1])


def aggregate_ballots(ballots: list[dict[str, Any]], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Globally optimize two disjoint, role-complete teams from valid ballots."""
    if not ballots:
        raise LineupValidationError('没有可聚合的有效选票')
    candidates = {row['player_id']: row for row in snapshot['candidates']}
    tier_counts = defaultdict(Counter)
    weapon_counts = defaultdict(Counter)
    function_counts = defaultdict(Counter)
    reason_rows = defaultdict(list)
    for ballot in ballots:
        for team_key in ('first_team', 'second_team'):
            tier = 'first' if team_key == 'first_team' else 'second'
            for member in ballot[team_key]:
                player_id = member['player_id']
                tier_counts[player_id][tier] += 1
                weapon_counts[player_id][member['weapon_role']] += 1
                function_counts[player_id][member['function_role']] += 1
                reason_rows[player_id].append({**member, 'tier': tier})

    zero = (0, 0, 0, 0, 0, 0)
    # state: first count, second count, first AWP, second AWP, function masks
    states = {(0, 0, 0, 0, 0, 0): (zero, [])}
    role_bits = {'opener': 1, 'support': 2, 'closer': 4, 'flex': 0}
    ordered = sorted(candidates.values(), key=lambda row: row['player_id'])
    for row in ordered:
        player_id = row['player_id']
        next_states = dict(states)
        total_points = 2 * tier_counts[player_id]['first'] + tier_counts[player_id]['second']
        pwr = int(round(float(row['metrics'].get('pwr_rating') or 0) * 10000))
        matches = int(row['metrics'].get('match_count') or 0)
        for state, (score, path) in states.items():
            fc, sc, fa, sa, fm, sm = state
            for team in ('first', 'second'):
                if (team == 'first' and fc >= 5) or (team == 'second' and sc >= 5):
                    continue
                for weapon in row['allowed_weapon_roles']:
                    is_awp = int(weapon == 'awper')
                    if (team == 'first' and fa + is_awp > 1) or (team == 'second' and sa + is_awp > 1):
                        continue
                    for function in row['allowed_function_roles']:
                        bit = role_bits[function]
                        if team == 'first':
                            new_state = (fc + 1, sc, fa + is_awp, sa, fm | bit, sm)
                        else:
                            new_state = (fc, sc + 1, fa, sa + is_awp, fm, sm | bit)
                        addition = (
                            total_points,
                            tier_counts[player_id][team],
                            weapon_counts[player_id][weapon],
                            function_counts[player_id][function],
                            pwr,
                            matches,
                        )
                        candidate = (_add_score(score, addition),
                                     path + [(player_id, team, weapon, function)])
                        if _prefer(candidate, next_states.get(new_state)):
                            next_states[new_state] = candidate
        states = next_states
    final = states.get((5, 5, 1, 1, 7, 7))
    if not final:
        raise LineupValidationError('候选人角色组合无法同时组成两套完整阵容')

    def representative_reason(player_id: str, team: str, weapon: str, function: str):
        rows = reason_rows[player_id]
        rows.sort(key=lambda item: (
            -(item['tier'] == team), -(item['weapon_role'] == weapon),
            -(item['function_role'] == function), -len(item['evidence']),
            len(item['reason']), item['reason'],
        ))
        return rows[0] if rows else {'reason': '根据多轮评审共识入选。', 'evidence': ['pwr_rating']}

    result = {'first_team': [], 'second_team': []}
    ballot_count = len(ballots)
    for player_id, team, weapon, function in final[1]:
        row = candidates[player_id]
        selected = tier_counts[player_id]['first'] + tier_counts[player_id]['second']
        reason = representative_reason(player_id, team, weapon, function)
        member = {
            'player_id': player_id,
            'name': row['player_name'],
            'avatar': row.get('avatar') or '',
            'weapon_role': weapon,
            'function_role': function,
            'reason': reason['reason'],
            'evidence': {key: row['metrics'][key] for key in reason['evidence']},
            'selection_rate': round(selected / ballot_count, 4),
            'first_team_rate': round(tier_counts[player_id]['first'] / ballot_count, 4),
            'second_team_rate': round(tier_counts[player_id]['second'] / ballot_count, 4),
            'demo_coverage': row['demo_coverage'],
        }
        result[f'{team}_team'].append(member)
    for team_key in ('first_team', 'second_team'):
        result[team_key].sort(key=lambda member: (
            member['weapon_role'] != 'awper',
            {'opener': 0, 'support': 1, 'closer': 2, 'flex': 3}[member['function_role']],
            -member['selection_rate'], member['player_id'],
        ))
    result.update({
        'valid_ballots': ballot_count,
        'target_ballots': SEASON_LINEUP_BALLOTS,
        'data_cutoff': snapshot['season'].get('data_cutoff'),
        'minimum_matches': snapshot['eligibility']['minimum_matches'],
        'candidate_count': snapshot['eligibility']['candidate_count'],
        'method': f'候选人满足半数出勤门槛；DeepSeek 进行 {SEASON_LINEUP_BALLOTS} 轮分层评审，一阵票计 2 分、二阵票计 1 分，再在两阵角色完整且 10 人不重复的约束下聚合。',
    })
    return result


def _decode(value: str | None, default: Any) -> Any:
    try:
        return json.loads(value or '')
    except (TypeError, ValueError):
        return default


def public_lineup_payload(cup: str) -> dict[str, Any] | None:
    latest = (SeasonLineupRun.select().where(SeasonLineupRun.cup_name == cup)
              .order_by(SeasonLineupRun.id.desc()).first())
    completed = (SeasonLineupRun.select().where(
        SeasonLineupRun.cup_name == cup,
        SeasonLineupRun.status == 'completed',
        SeasonLineupRun.result_json.is_null(False),
    ).order_by(SeasonLineupRun.id.desc()).first())
    if not latest and not completed:
        return None
    if not completed:
        return {
            'status': latest.status,
            'is_final': False,
            'message': latest.error_message if latest.status == 'insufficient_data' else None,
        }
    payload = _decode(completed.result_json, {})
    payload.update({
        'status': 'completed',
        'is_final': bool(completed.is_final),
        'generated_at': completed.generated_at.isoformat() if completed.generated_at else None,
        'refreshing': bool(latest and latest.id != completed.id and
                           latest.status in ('pending', 'queued', 'generating')),
        'finalizing_failed': bool(latest and latest.id != completed.id and
                                  latest.status == 'failed' and
                                  (Season.get_by_cup(cup) or {}).get('status') == 'archived'),
    })
    return payload


def admin_lineup_payload(cup: str) -> dict[str, Any]:
    rows = (SeasonLineupRun.select().where(SeasonLineupRun.cup_name == cup)
            .order_by(SeasonLineupRun.id.desc()).limit(10))
    history = []
    for row in rows:
        history.append({
            'id': row.id,
            'status': row.status,
            'is_final': bool(row.is_final),
            'ballot_target': int(row.ballot_target or SEASON_LINEUP_BALLOTS),
            'valid_ballots': int(row.valid_ballots or 0),
            'model_name': row.model_name,
            'error_message': row.error_message,
            'total_tokens': row.total_tokens,
            'created_at': row.created_at.isoformat() if row.created_at else None,
            'generated_at': row.generated_at.isoformat() if row.generated_at else None,
        })
    return {'current': public_lineup_payload(cup), 'history': history}
