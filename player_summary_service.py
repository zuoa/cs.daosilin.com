"""Build trustworthy season inputs and generate structured DeepSeek summaries."""
import hashlib
import json
import re
from datetime import datetime

from openai import OpenAI

from config import (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_NAME,
                    LLM_REQUEST_TIMEOUT, PLAYER_SUMMARY_PROMPT_VERSION)
from database import (MatchPlayer, Player, PlayerSeasonSummary, Season)


TRUSTED_ZERO_FIELDS = {
    'match_count': '比赛场次',
    'win_count': '胜场',
    'total_rounds': '总回合',
    'total_kills': '总击杀',
    'total_deaths': '总死亡',
    'total_assists': '总助攻',
}

OPTIONAL_FIELDS = {
    'avg_pw_rating': 'PWR Rating',
    'kd_ratio': 'K/D',
    'avg_adpr': 'ADR',
    'avg_kast': 'KAST',
    'avg_headshot_ratio': '爆头率',
    'total_first_kills': '首杀',
    'total_first_deaths': '首死',
    'opening_duel_win_rate': '开局对枪胜率',
    'total_2k': '2K 回合',
    'total_3k': '3K 回合',
    'total_4k': '4K 回合',
    'total_5k': '5K 回合',
    'total_trade_frags': '补枪击杀',
    'total_mvp': 'MVP 次数',
    'total_snipe_num': '狙击击杀',
    'total_utility_damage': '道具伤害',
}

RANK_FIELDS = {
    'avg_pw_rating': 'PWR Rating',
    'kd_ratio': 'K/D',
    'win_rate': '胜率',
    'avg_adpr': 'ADR',
    'avg_headshot_ratio': '爆头率',
    'total_mvp': 'MVP 次数',
}

DEMO_FIELDS = {
    'demo_rating': 'Demo Rating',
    'death_trade_rate': '被补枪率',
    'opening_round_conversion': '首杀转回合胜率',
    'total_clutches_won': '残局胜利',
    'flash_assists': '闪光助攻',
    'enemies_per_flash': '每颗闪光致盲敌人',
    'enemy_flash_seconds': '敌方致盲总秒数',
    'utility_damage_per_throw': '每颗道具伤害',
    'ct_adr': 'CT ADR',
    't_adr': 'T ADR',
    'ct_kast': 'CT KAST',
    't_kast': 'T KAST',
}


def llm_configured():
    return bool(LLM_API_KEY and LLM_BASE_URL and LLM_MODEL_NAME)


def _present_nonzero(value):
    if value is None or isinstance(value, bool):
        return False
    try:
        return float(value) != 0
    except (TypeError, ValueError):
        return bool(str(value).strip())


def _number(value, digits=4):
    number = float(value)
    return int(number) if number.is_integer() else round(number, digits)


def _ratio(numerator, denominator):
    if denominator is None or float(denominator) <= 0:
        return None
    return round(float(numerator) / float(denominator), 4)


def _player_name(player_id):
    player = Player.get_or_none(Player.player_id == player_id)
    if not player:
        return player_id
    return player.alias_name or player.nickname or player_id


def _peer_rows(cup_name):
    query = (MatchPlayer.select(MatchPlayer.player_id)
             .where(MatchPlayer.cup_name == cup_name).distinct())
    player_ids = [record.player_id for record in query]
    aggregates = MatchPlayer.get_match_exploits(cup_name, player_ids, None)
    return [
        (player_id, aggregates[str(player_id)])
        for player_id in player_ids if str(player_id) in aggregates
    ]


def build_summary_input(cup_name, player_id, peers=None):
    """Return a prompt-safe snapshot. Missing/ambiguous zero metrics are omitted."""
    stats = MatchPlayer.get_match_exploit(cup_name, player_id, None)
    if not stats:
        return None
    season = Season.get_by_cup(cup_name) or {}
    match_count = int(stats.get('match_count') or 0)
    wins = int(stats.get('win_count') or 0)
    rounds = int(stats.get('total_rounds') or 0)
    performance = {}
    for key, label in TRUSTED_ZERO_FIELDS.items():
        value = stats.get(key)
        if value is not None:
            performance[label] = _number(value)

    losses = max(0, match_count - wins)
    performance['负场'] = losses
    win_rate = _ratio(wins, match_count)
    if win_rate is not None:
        performance['胜率'] = win_rate
    kd_ratio = _ratio(stats.get('total_kills'), stats.get('total_deaths'))
    if kd_ratio is not None:
        performance['K/D'] = kd_ratio

    # Legacy aggregates use COALESCE(…, 0). Optional zeroes are therefore
    # ambiguous and deliberately excluded from the model input.
    for key, label in OPTIONAL_FIELDS.items():
        if label in performance:
            continue
        value = stats.get(key)
        if _present_nonzero(value):
            performance[label] = _number(value)

    peer_rows = peers if peers is not None else _peer_rows(cup_name)
    rankings = []
    for key, label in RANK_FIELDS.items():
        current = stats.get(key)
        if not _present_nonzero(current):
            continue
        eligible = [
            (peer_id, float(peer_stats[key]))
            for peer_id, peer_stats in peer_rows
            if _present_nonzero(peer_stats.get(key))
        ]
        eligible.sort(key=lambda item: item[1], reverse=True)
        rank = next((index for index, item in enumerate(eligible, 1)
                     if item[0] == player_id), None)
        if rank:
            rankings.append({'指标': label, '排名': rank, '有效选手数': len(eligible)})

    maps = []
    for item in MatchPlayer.get_player_map_stats(cup_name, player_id, None)[:6]:
        row = {
            '地图': item.get('map_name') or item.get('map_name_en') or '未知地图',
            '场次': int(item.get('match_count') or 0),
            '胜场': int(item.get('win_count') or 0),
        }
        for key, label in (('avg_rating', 'Rating'), ('kd_ratio', 'K/D'),
                           ('avg_adpr', 'ADR'), ('avg_kast', 'KAST')):
            if _present_nonzero(item.get(key)):
                row[label] = _number(item[key])
        maps.append(row)

    days = []
    cup_days = sorted(MatchPlayer.get_cup_day_set(cup_name) or [])
    day_stats_map = (
        MatchPlayer.get_match_exploits_by_day(cup_name, [player_id])
        if cup_days else {}
    )
    for play_day in cup_days:
        day_stats = day_stats_map.get((str(player_id), play_day))
        if not day_stats:
            continue
        row = {'比赛日': play_day, '场次': int(day_stats.get('match_count') or 0)}
        if _present_nonzero(day_stats.get('avg_pw_rating')):
            row['PWR Rating'] = _number(day_stats['avg_pw_rating'])
        days.append(row)

    demo = None
    demo_data = stats.get('demo_data')
    coverage = stats.get('demo_coverage') or {}
    if demo_data and int(coverage.get('completed') or 0) > 0:
        metrics = {}
        for key, label in DEMO_FIELDS.items():
            if _present_nonzero(demo_data.get(key)):
                metrics[label] = _number(demo_data[key])
        demo = {
            '覆盖场次': int(coverage.get('completed') or 0),
            '赛季总场次': int(coverage.get('total') or match_count),
            '指标': metrics,
        }

    snapshot = {
        '选手': _player_name(player_id),
        '赛季': season.get('cup_alias') or season.get('name') or cup_name,
        '样本': {'比赛场次': match_count, '总回合': rounds},
        '表现': performance,
    }
    if rankings:
        snapshot['同赛季排名'] = rankings
    if maps:
        snapshot['地图表现'] = maps
    if days:
        snapshot['比赛日走势'] = days
    if demo:
        snapshot['Demo 数据'] = demo
    return snapshot


def snapshot_hash(snapshot):
    body = {
        'prompt_version': PLAYER_SUMMARY_PROMPT_VERSION,
        'model': LLM_MODEL_NAME,
        'input': snapshot,
    }
    encoded = json.dumps(body, ensure_ascii=False, sort_keys=True,
                         separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


SYSTEM_PROMPT = """你是一名严谨、专业又有一点幽默感的 CS2 数据分析师。
你只能依据用户给出的 JSON 数据写赛季球探报告，不得补全缺失数据，不得把没有提供的指标推断为 0，
不得虚构选手位置、武器偏好、战术职责或比赛事件。样本较少时必须明确保持谨慎。
幽默应针对比赛表现，轻巧克制，不攻击人格、身份或外貌。
请只输出 JSON 对象，字段必须为 headline、overview、strength、weakness、style。
headline 为 6-18 个汉字；overview 为 80-140 个汉字；其余每项为 20-55 个汉字。
strength 写最有证据的优势；weakness 写短板或数据不足时的观察项；style 概括打法画像。
不要输出 Markdown，不要重复 JSON 之外的文字。"""


def _validate_output(raw):
    if not raw or not str(raw).strip():
        raise ValueError('DeepSeek 返回空内容')
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('DeepSeek 返回的不是有效 JSON') from exc
    if not isinstance(value, dict):
        raise ValueError('DeepSeek 返回结构不是对象')
    limits = {
        'headline': (2, 36), 'overview': (40, 220),
        'strength': (8, 100), 'weakness': (8, 100), 'style': (8, 100),
    }
    result = {}
    for key, (minimum, maximum) in limits.items():
        text = re.sub(r'\s+', ' ', str(value.get(key) or '')).strip()
        if len(text) < minimum or len(text) > maximum:
            raise ValueError(f'DeepSeek 字段 {key} 长度不合规')
        result[key] = text
    return result


def generate_summary(snapshot, client=None):
    if not llm_configured():
        raise ValueError('LLM_API_KEY 未配置')
    client = client or OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=LLM_REQUEST_TIMEOUT,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=LLM_MODEL_NAME,
        messages=[
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': '请分析以下赛季数据并输出 json：\n' +
             json.dumps(snapshot, ensure_ascii=False, sort_keys=True)},
        ],
        response_format={'type': 'json_object'},
        max_tokens=600,
        temperature=0.7,
        stream=False,
        extra_body={'thinking': {'type': 'disabled'}},
    )
    content = response.choices[0].message.content if response.choices else ''
    result = _validate_output(content)
    usage = getattr(response, 'usage', None)
    result['usage'] = {
        'prompt_tokens': getattr(usage, 'prompt_tokens', None),
        'completion_tokens': getattr(usage, 'completion_tokens', None),
        'total_tokens': getattr(usage, 'total_tokens', None),
    }
    return result


def get_public_summary(cup_name, player_id):
    row = PlayerSeasonSummary.get_or_none(
        PlayerSeasonSummary.cup_name == cup_name,
        PlayerSeasonSummary.player_id == player_id,
    )
    return row.public_payload() if row else None


def admin_row(row):
    player = Player.get_or_none(Player.player_id == row.player_id)
    return {
        'id': row.id,
        'player_id': row.player_id,
        'player_name': ((player.alias_name or player.nickname) if player else row.player_id),
        'cup_name': row.cup_name,
        'status': row.status,
        'headline': row.headline,
        'attempt_count': row.attempt_count,
        'model_name': row.model_name,
        'total_tokens': row.total_tokens,
        'error_message': row.error_message,
        'generated_at': row.generated_at.isoformat() if row.generated_at else None,
        'updated_at': row.updated_at.isoformat() if row.updated_at else None,
    }
