"""Manage reversible main-player and child-account relationships."""

from typing import Dict, Iterable, List

from database import MatchPlayer, Player, fn


class PlayerIdentityError(ValueError):
    def __init__(self, message: str, *, conflict_match_ids=None):
        super().__init__(message)
        self.conflict_match_ids = list(conflict_match_ids or [])


def player_account_payload(player: Player) -> Dict:
    canonical = Player.canonical_player(player)
    children = []
    if canonical and canonical.player_id == player.player_id:
        children = list(
            Player.select(Player.player_id, Player.nickname, Player.alias_name, Player.steam_id)
            .where(Player.parent_player_id == player.player_id)
            .order_by(Player.nickname, Player.player_id)
            .dicts()
        )
    return {
        'canonical_player_id': canonical.player_id if canonical else player.player_id,
        'parent_player_id': player.parent_player_id,
        'child_accounts': children,
    }


def _normalized_ids(values: Iterable[str]) -> List[str]:
    return list(dict.fromkeys(
        str(value or '').strip() for value in (values or []) if str(value or '').strip()
    ))


def _affected_cups(account_ids: Iterable[str]) -> List[str]:
    rows = (MatchPlayer.select(MatchPlayer.cup_name)
            .where(MatchPlayer.player_id.in_(_normalized_ids(account_ids)),
                   MatchPlayer.cup_name.is_null(False))
            .distinct())
    return sorted(str(row.cup_name) for row in rows if row.cup_name)


def bind_child_accounts(parent_player_id: str, child_player_ids: Iterable[str]) -> Dict:
    parent_player_id = str(parent_player_id or '').strip()
    child_player_ids = _normalized_ids(child_player_ids)
    parent = Player.get_or_none(Player.player_id == parent_player_id)
    if parent is None:
        raise PlayerIdentityError('主玩家不存在')
    if parent.parent_player_id:
        raise PlayerIdentityError('子账号不能作为主玩家，请先解除其现有归属')
    if not child_player_ids:
        raise PlayerIdentityError('请至少选择一个子账号')
    if parent_player_id in child_player_ids:
        raise PlayerIdentityError('主玩家不能绑定为自己的子账号')

    children = {
        row.player_id: row for row in
        Player.select().where(Player.player_id.in_(child_player_ids))
    }
    missing = [player_id for player_id in child_player_ids if player_id not in children]
    if missing:
        raise PlayerIdentityError(f'子账号不存在：{", ".join(missing)}')
    for child in children.values():
        if child.parent_player_id and child.parent_player_id != parent_player_id:
            raise PlayerIdentityError(
                f'账号 {child.player_id} 已归属于 {child.parent_player_id}'
            )
        if Player.select().where(Player.parent_player_id == child.player_id).exists():
            raise PlayerIdentityError(
                f'账号 {child.player_id} 已有子账号，请先解除原账号组'
            )

    family_ids = _normalized_ids([
        *Player.account_ids(parent_player_id), *child_player_ids,
    ])
    conflicts = list(
        MatchPlayer.select(MatchPlayer.match_id)
        .where(MatchPlayer.player_id.in_(family_ids))
        .group_by(MatchPlayer.match_id)
        .having(fn.COUNT(fn.DISTINCT(MatchPlayer.player_id)) > 1)
        .order_by(MatchPlayer.match_id)
        .limit(20)
        .tuples()
    )
    conflict_ids = [row[0] for row in conflicts]
    if conflict_ids:
        raise PlayerIdentityError(
            '这些账号曾在同一场比赛中同时出现，不能归集',
            conflict_match_ids=conflict_ids,
        )

    cups = _affected_cups(family_ids)
    group_in_library = Player.select().where(
        Player.player_id.in_(family_ids),
        Player.in_library == True,
    ).exists()
    with Player._meta.database.atomic():
        if group_in_library and not parent.in_library:
            (Player.update(in_library=True)
             .where(Player.player_id == parent_player_id)
             .execute())
        (Player.update(parent_player_id=parent_player_id)
         .where(Player.player_id.in_(child_player_ids))
         .execute())
    return {
        'canonical_player_id': parent_player_id,
        'child_player_ids': Player.account_ids(parent_player_id)[1:],
        'affected_cups': cups,
    }


def unbind_child_account(child_player_id: str) -> Dict:
    child_player_id = str(child_player_id or '').strip()
    child = Player.get_or_none(Player.player_id == child_player_id)
    if child is None:
        raise PlayerIdentityError('子账号不存在')
    if not child.parent_player_id:
        raise PlayerIdentityError('该账号当前不是子账号')
    parent_player_id = child.parent_player_id
    cups = _affected_cups([*Player.account_ids(parent_player_id), child_player_id])
    child.parent_player_id = None
    child.save()
    return {
        'canonical_player_id': parent_player_id,
        'unbound_player_id': child_player_id,
        'affected_cups': cups,
    }
