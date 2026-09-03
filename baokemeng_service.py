"""Pure draft tracking plus persistence/query helpers for Baokemeng."""
from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from peewee import IntegrityError

from database import DraftPlayer, DraftSession, DraftTeam, db


STEAM64_RE = re.compile(r'^\d{17}$')
AREA_RE = re.compile(r'^area(\d+)$')
GROUP_HTML_RE = re.compile(r'分组\s*<b[^>]*>([^<]+)</b>', re.IGNORECASE)
GROUP_TEXT_RE = re.compile(r'分组\s*([^\s<]+)', re.IGNORECASE)


class DraftValidationError(ValueError):
    pass


def _clean_text(value: Any) -> str:
    return unicodedata.normalize('NFKC', str(value or '')).strip()


def _nullable_id(value: Any) -> str | None:
    value = _clean_text(value)
    return value if value and value != '0' else None


def normalize_player(card: dict[str, Any]) -> dict[str, Any]:
    nickname = _clean_text(card.get('nickname'))
    steam_id = _clean_text(card.get('hideSteamID'))
    steam_id = steam_id if STEAM64_RE.fullmatch(steam_id) else None
    site_id = _nullable_id(card.get('hideID'))
    if site_id and site_id.casefold().startswith('registered_'):
        site_id = None
    zbj_id = _nullable_id(card.get('hideZBJ_ID'))
    if not nickname:
        nickname = steam_id or site_id or zbj_id or '未命名选手'
    return {
        'nickname': nickname,
        'steam_id': steam_id,
        'site_id': site_id,
        'zbj_id': zbj_id,
        'needs_steam': steam_id is None,
        'steam_id_source': 'captured' if steam_id else None,
    }


def _player_identity(player: dict[str, Any]) -> str:
    if player['steam_id']:
        return f"steam:{player['steam_id']}"
    if player['site_id']:
        return f"site:{player['site_id'].casefold()}"
    return f"nickname:{player['nickname'].casefold()}"


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _area_number(area: str) -> int:
    match = AREA_RE.fullmatch(area)
    if not match:
        raise DraftValidationError(f'无法识别队伍区域 {area!r}')
    return int(match.group(1))


def _area_names(board: dict[str, Any], area_count: int | None) -> list[str]:
    top = board.get('topArea')
    if not isinstance(top, dict):
        raise DraftValidationError('snapshot.topArea 缺失')
    names = [name for name in top if AREA_RE.fullmatch(str(name))]
    if not names:
        raise DraftValidationError('topArea 中没有队伍区域')
    names = sorted(names, key=_area_number)
    if area_count:
        configured = [f'area{index}' for index in range(1, area_count + 1)]
        if set(names) == set(configured):
            return configured
    return names


def board_fingerprint(board: dict[str, Any], area_count: int | None = None) -> str:
    """Fingerprint only ordered top-area positions, ignoring ready-state noise."""
    top = board.get('topArea') or {}
    rows = []
    for area in _area_names(board, area_count):
        cards = top.get(area)
        if not isinstance(cards, list):
            cards = []
        rows.append({
            'area': area,
            'players': [_player_identity(normalize_player(card or {})) for card in cards],
        })
    return _fingerprint(rows)


def raw_roll_fingerprint(team_bat: Any) -> str | None:
    if not isinstance(team_bat, list) or not team_bat:
        return None
    rows = [{
        'team_num': item.get('teamNum'),
        'roll': item.get('random'),
        'desc': _clean_text(item.get('desc')),
    } for item in team_bat if isinstance(item, dict)]
    return _fingerprint(sorted(rows, key=lambda row: str(row['team_num'])))


def _group_name(item: dict[str, Any]) -> str:
    direct = _clean_text(item.get('groupName') or item.get('group_name'))
    if direct:
        return direct
    desc = _clean_text(item.get('desc'))
    match = GROUP_HTML_RE.search(desc)
    if match:
        return _clean_text(html.unescape(match.group(1)))
    plain = re.sub(r'<[^>]+>', ' ', html.unescape(desc))
    match = GROUP_TEXT_RE.search(plain)
    return _clean_text(match.group(1)) if match else ''


def build_final_snapshot(
    board: dict[str, Any],
    team_bat: Any,
    *,
    area_count: int | None,
    started_at: datetime | None,
    completed_at: datetime,
) -> dict[str, Any]:
    areas = _area_names(board, area_count)
    top = board['topArea']
    teams: list[dict[str, Any]] = []
    expected_team_nums = set()
    for area in areas:
        cards = top.get(area)
        if not isinstance(cards, list) or not cards:
            raise DraftValidationError(f'{area} 尚无队员')
        players = [normalize_player(card or {}) for card in cards]
        identities = [_player_identity(player) for player in players]
        duplicates = [key for key, count in Counter(identities).items() if count > 1]
        if duplicates:
            raise DraftValidationError(f'{area} 存在重复选手标识')
        team_num = _area_number(area) - 1
        expected_team_nums.add(team_num)
        teams.append({
            'team_num': team_num,
            'area': area,
            'roster_size': len(players),
            'players': [
                {'slot': slot, 'is_captain': slot == 1, **player}
                for slot, player in enumerate(players, 1)
            ],
        })

    if not isinstance(team_bat, list):
        raise DraftValidationError('teamBat 缺失')
    rolls: dict[int, dict[str, Any]] = {}
    for item in team_bat:
        if not isinstance(item, dict):
            raise DraftValidationError('teamBat 项格式错误')
        try:
            team_num = int(item.get('teamNum'))
        except (TypeError, ValueError) as exc:
            raise DraftValidationError('teamBat.teamNum 无效') from exc
        if team_num in rolls:
            raise DraftValidationError('teamBat 包含重复队伍')
        group_name = _group_name(item)
        if not group_name:
            raise DraftValidationError(f'队伍 {team_num} 缺少分组')
        try:
            roll = int(item.get('random'))
        except (TypeError, ValueError) as exc:
            raise DraftValidationError(f'队伍 {team_num} roll 无效') from exc
        rolls[team_num] = {'group_name': group_name, 'roll': roll}

    if set(rolls) != expected_team_nums:
        raise DraftValidationError('teamBat 未完整覆盖当前队伍')
    group_counts = Counter(item['group_name'] for item in rolls.values())
    if any(count != 2 for count in group_counts.values()):
        raise DraftValidationError('每个分组必须恰好包含两支队伍')

    for team in teams:
        team.update(rolls[team['team_num']])
    roster_shape = [{
        'area': team['area'],
        'team_num': team['team_num'],
        'players': [
            {'slot': player['slot'], 'identity': _player_identity(player)}
            for player in team['players']
        ],
    } for team in teams]
    roll_shape = [{
        'team_num': team['team_num'],
        'group_name': team['group_name'],
        'roll': team['roll'],
    } for team in teams]
    return {
        'started_at': started_at,
        'completed_at': completed_at,
        'team_count': len(teams),
        'roster_fingerprint': _fingerprint(roster_shape),
        'roll_fingerprint': _fingerprint(roll_shape),
        'teams': teams,
    }


@dataclass
class _PendingDraft:
    snapshot: dict[str, Any]
    stable_since: datetime
    key: tuple[str, str]
    raw_roll_key: str
    emitted: bool = False


class DraftTracker:
    """State machine with no network or database dependency."""

    def __init__(self, stable_seconds: float = 5.0):
        self.stable_seconds = max(0.0, float(stable_seconds))
        self.board: dict[str, Any] | None = None
        self.area_count: int | None = None
        self.board_key: str | None = None
        self.baseline_roll_key: str | None = None
        self.committed_roll_key: str | None = None
        self.started_at: datetime | None = None
        self.active = False
        self.pending: _PendingDraft | None = None

    def ingest_loading(self, args: list[Any], now: datetime) -> None:
        if len(args) < 3 or not isinstance(args[1], dict) or not isinstance(args[2], dict):
            raise DraftValidationError('loading 参数格式错误')
        settings = args[2].get('appSettings') or {}
        area_count = _positive_int(settings.get('topAreaNum'))
        board = args[1]
        board_key = board_fingerprint(board, area_count)
        team_bat = (args[2].get('adminToC') or {}).get('teamBat')
        roll_key = raw_roll_fingerprint(team_bat)

        # A reconnect loading packet is also the first authoritative state after
        # the gap. Keep an in-progress round alive and evaluate its current roll;
        # otherwise a disconnect between the last pick and roll would lose it.
        if self.active:
            if self.board_key is not None and board_key != self.board_key:
                self.pending = None
            self.board = board
            self.area_count = area_count
            self.board_key = board_key
            self._observe_roll(team_bat, now)
            return

        # Cold starts and reconnects after a completed round only establish a
        # baseline. This prevents stale complete boards from being persisted.
        self.board = board
        self.area_count = area_count
        self.board_key = board_key
        self.baseline_roll_key = roll_key
        self.committed_roll_key = None
        self.started_at = None
        self.active = False
        self.pending = None

    def ingest_update(self, args: list[Any], now: datetime) -> None:
        if len(args) < 2 or not isinstance(args[0], str) or not isinstance(args[1], dict):
            raise DraftValidationError('updatePlayerPosition 参数格式错误')
        try:
            update = json.loads(args[0])
        except json.JSONDecodeError as exc:
            raise DraftValidationError('updatePlayerPosition JSON 无效') from exc
        settings = args[1].get('appSettings') or {}
        configured_count = _positive_int(settings.get('topAreaNum'))
        if configured_count:
            self.area_count = configured_count
        snapshot = update.get('snapshot')
        if isinstance(snapshot, dict):
            next_key = board_fingerprint(snapshot, self.area_count)
            if self.board_key is not None and next_key != self.board_key:
                if not self.active:
                    self.started_at = now
                self.active = True
                self.pending = None
            self.board = snapshot
            self.board_key = next_key

        team_bat = (args[1].get('adminToC') or {}).get('teamBat')
        self._observe_roll(team_bat, now)

    def _observe_roll(self, team_bat: Any, now: datetime) -> None:
        if not self.active or self.board is None:
            return
        roll_key = raw_roll_fingerprint(team_bat)
        if not roll_key or roll_key in {self.baseline_roll_key, self.committed_roll_key}:
            self.pending = None
            return
        try:
            final = build_final_snapshot(
                self.board,
                team_bat,
                area_count=self.area_count,
                started_at=self.started_at,
                completed_at=now,
            )
        except DraftValidationError:
            self.pending = None
            return
        key = (final['roster_fingerprint'], final['roll_fingerprint'])
        if (self.pending is None or self.pending.key != key
                or self.pending.raw_roll_key != roll_key):
            self.pending = _PendingDraft(final, now, key, roll_key)

    def poll(self, now: datetime) -> dict[str, Any] | None:
        pending = self.pending
        if pending is None or pending.emitted:
            return None
        if (now - pending.stable_since).total_seconds() < self.stable_seconds:
            return None
        pending.emitted = True
        pending.snapshot['completed_at'] = pending.stable_since
        return pending.snapshot

    def commit_succeeded(self) -> None:
        if self.pending is None:
            return
        self.committed_roll_key = self.pending.raw_roll_key
        self.baseline_roll_key = self.committed_roll_key
        self.pending = None
        self.started_at = None
        self.active = False

    def commit_failed(self) -> None:
        if self.pending is not None:
            self.pending.emitted = False


def _positive_int(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def persist_final_draft(snapshot: dict[str, Any]) -> tuple[DraftSession, bool]:
    completed_at = snapshot['completed_at']
    play_day = (completed_at - timedelta(hours=3)).strftime('%Y%m%d')
    lookup = (
        (DraftSession.play_day == play_day)
        & (DraftSession.roster_fingerprint == snapshot['roster_fingerprint'])
        & (DraftSession.roll_fingerprint == snapshot['roll_fingerprint'])
    )

    def activate_existing(existing: DraftSession) -> tuple[DraftSession, bool]:
        with db.atomic():
            (DraftSession.update(status='superseded')
             .where(
                 (DraftSession.play_day == play_day)
                 & (DraftSession.roster_fingerprint == snapshot['roster_fingerprint'])
                 & (DraftSession.status == 'complete')
                 & (DraftSession.id != existing.id)
             ).execute())
            (DraftSession.update(
                started_at=snapshot.get('started_at'),
                completed_at=completed_at,
                team_count=snapshot['team_count'],
                status='complete',
             ).where(DraftSession.id == existing.id).execute())
        return DraftSession.get_by_id(existing.id), False

    existing = DraftSession.get_or_none(lookup)
    if existing:
        return activate_existing(existing)
    try:
        with db.atomic():
            (DraftSession.update(status='superseded')
             .where(
                 (DraftSession.play_day == play_day)
                 & (DraftSession.roster_fingerprint == snapshot['roster_fingerprint'])
                 & (DraftSession.status == 'complete')
             ).execute())
            session = DraftSession.create(
                play_day=play_day,
                started_at=snapshot.get('started_at'),
                completed_at=completed_at,
                roster_fingerprint=snapshot['roster_fingerprint'],
                roll_fingerprint=snapshot['roll_fingerprint'],
                team_count=snapshot['team_count'],
                status='complete',
            )
            for team in snapshot['teams']:
                DraftTeam.create(
                    session=session,
                    team_num=team['team_num'],
                    area=team['area'],
                    roster_size=team['roster_size'],
                    captain_nickname=team['players'][0]['nickname'],
                    group_name=team['group_name'],
                    roll=team['roll'],
                )
                DraftPlayer.insert_many([
                    {
                        'session': session.id,
                        'team_num': team['team_num'],
                        **player,
                    }
                    for player in team['players']
                ]).execute()
        return session, True
    except IntegrityError:
        session = DraftSession.get(lookup)
        return activate_existing(session)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def public_draft_payload(day: str | None = None, session_id: int | None = None) -> dict[str, Any]:
    complete = DraftSession.select().where(DraftSession.status == 'complete')
    days = [row.play_day for row in (
        complete.select(DraftSession.play_day)
        .distinct()
        .order_by(DraftSession.play_day.desc())
    )]

    selected = None
    if session_id is not None:
        selected = DraftSession.get_or_none(
            (DraftSession.id == session_id) & (DraftSession.status == 'complete')
        )
        if selected is None:
            raise DraftValidationError('选人终稿不存在')
        day = selected.play_day
    if not day:
        day = days[0] if days else None

    sessions: list[DraftSession] = []
    if day:
        sessions = list(
            complete.where(DraftSession.play_day == day)
            .order_by(DraftSession.completed_at.desc(), DraftSession.id.desc())
        )
    if selected is None and sessions:
        selected = sessions[0]

    detail = None
    if selected:
        player_rows: dict[int, list[dict[str, Any]]] = {}
        for player in (DraftPlayer.select()
                       .where(DraftPlayer.session == selected)
                       .order_by(DraftPlayer.team_num, DraftPlayer.slot)):
            player_rows.setdefault(player.team_num, []).append({
                'slot': player.slot,
                'is_captain': bool(player.is_captain),
                'nickname': player.nickname,
                'needs_steam': bool(player.needs_steam),
            })
        groups: dict[str, list[dict[str, Any]]] = {}
        for team in (DraftTeam.select()
                     .where(DraftTeam.session == selected)
                     .order_by(DraftTeam.id)):
            groups.setdefault(team.group_name, []).append({
                'team_num': team.team_num,
                'area': team.area,
                'roster_size': team.roster_size,
                'captain_nickname': team.captain_nickname,
                'roll': team.roll,
                'players': player_rows.get(team.team_num, []),
            })
        detail = {
            'id': selected.id,
            'play_day': selected.play_day,
            'started_at': _iso(selected.started_at),
            'completed_at': _iso(selected.completed_at),
            'team_count': selected.team_count,
            'player_count': sum(len(players) for players in player_rows.values()),
            'groups': [
                {'name': name, 'teams': sorted(teams, key=lambda item: item['roll'])}
                for name, teams in groups.items()
            ],
        }
    return {
        'days': days,
        'sessions': [{
            'id': row.id,
            'play_day': row.play_day,
            'completed_at': _iso(row.completed_at),
            'team_count': row.team_count,
        } for row in sessions],
        'selected_session': detail,
    }
