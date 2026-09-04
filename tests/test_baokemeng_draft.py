import json
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from peewee import SqliteDatabase

from baokemeng_service import (
    DraftTracker,
    build_final_snapshot,
    draft_pick_summaries,
    persist_final_draft,
    public_draft_payload,
    summarize_draft_pick_records,
)
from database import DraftPlayer, DraftSession, DraftTeam, Player


def player(name, steam=True):
    digits = ''.join(character for character in name if character.isdigit()) or '1'
    return {
        'nickname': name,
        'hideSteamID': str(76561198000000000 + int(digits)) if steam else '',
        'hideID': name,
        'hideZBJ_ID': '0',
    }


def board(sizes, middle=0):
    return {
        'topArea': {
            f'area{team + 1}': [
                player(f'p{team + 1}_{slot + 1}', not (team == 0 and slot == 1))
                for slot in range(size)
            ]
            for team, size in enumerate(sizes)
        },
        'middleArea': [player(f'sub_{index}', False) for index in range(middle)],
        'bottomArea': [],
    }


def rolls(team_count, offset=0):
    return [
        {
            'teamNum': team,
            'random': offset + team + 1,
            'desc': f'<span class="team-group">分组 <b>{chr(65 + team // 2)}组</b></span>',
        }
        for team in range(team_count)
    ]


def loading_args(value, team_bat):
    return [
        'ok',
        value,
        {
            'appSettings': {'topAreaNum': len(value['topArea'])},
            'adminToC': {'teamBat': team_bat},
        },
    ]


def update_args(value, team_bat):
    return [
        json.dumps({'moved': [], 'changed': [], 'snapshot': value}, ensure_ascii=False),
        {'adminToC': {'teamBat': team_bat}},
    ]


class DraftTrackerTest(unittest.TestCase):
    def test_dynamic_teams_uneven_rosters_and_middle_substitutes(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=5)
        old = board([2] * 10)
        tracker.ingest_loading(loading_args(old, rolls(10)), now)
        self.assertIsNone(tracker.poll(now + timedelta(seconds=30)))

        drafting = board([1, 2, 3, 2, 2, 2, 2, 2, 2, 2], middle=5)
        tracker.ingest_update(update_args(drafting, rolls(10)), now + timedelta(seconds=1))
        self.assertIsNone(tracker.poll(now + timedelta(seconds=20)))

        final = board([2, 3, 2, 4, 2, 3, 2, 2, 3, 2], middle=7)
        tracker.ingest_update(update_args(final, rolls(10)), now + timedelta(seconds=20))
        tracker.ingest_update(update_args(final, rolls(10, offset=20)), now + timedelta(seconds=30))
        self.assertIsNone(tracker.poll(now + timedelta(seconds=34)))
        snapshot = tracker.poll(now + timedelta(seconds=35))

        self.assertEqual(snapshot['team_count'], 10)
        self.assertEqual([team['roster_size'] for team in snapshot['teams']],
                         [2, 3, 2, 4, 2, 3, 2, 2, 3, 2])
        self.assertTrue(snapshot['teams'][0]['players'][1]['needs_steam'])
        self.assertEqual(snapshot['teams'][0]['players'][0]['slot'], 1)
        self.assertTrue(snapshot['teams'][0]['players'][0]['is_captain'])

    def test_incomplete_roll_never_emits(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=0)
        tracker.ingest_loading(loading_args(board([2, 2]), rolls(2)), now)
        changed = board([3, 2], middle=1)
        tracker.ingest_update(update_args(changed, rolls(2)[:1]), now + timedelta(seconds=1))
        self.assertIsNone(tracker.poll(now + timedelta(seconds=2)))

    def test_board_change_resets_pending_stability(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=5)
        tracker.ingest_loading(loading_args(board([2, 2]), rolls(2)), now)
        first = board([3, 2])
        tracker.ingest_update(update_args(first, rolls(2, 10)), now + timedelta(seconds=1))
        second = board([2, 3])
        tracker.ingest_update(update_args(second, rolls(2, 10)), now + timedelta(seconds=4))
        self.assertIsNone(tracker.poll(now + timedelta(seconds=8)))
        self.assertIsNotNone(tracker.poll(now + timedelta(seconds=9)))

    def test_reconnect_keeps_matching_pending_final(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=5)
        tracker.ingest_loading(loading_args(board([2, 2]), rolls(2)), now)
        final = board([3, 2], middle=2)
        new_roll = rolls(2, 10)
        tracker.ingest_update(update_args(final, new_roll), now + timedelta(seconds=1))
        tracker.ingest_loading(loading_args(final, new_roll), now + timedelta(seconds=3))
        self.assertIsNotNone(tracker.poll(now + timedelta(seconds=6)))

    def test_reconnect_before_roll_preserves_active_round(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=5)
        initial = board([2, 2])
        final = board([3, 2], middle=2)
        old_roll = rolls(2)
        new_roll = rolls(2, 10)

        tracker.ingest_loading(loading_args(initial, old_roll), now)
        tracker.ingest_update(update_args(final, old_roll), now + timedelta(seconds=1))
        tracker.ingest_loading(loading_args(final, new_roll), now + timedelta(seconds=2))

        snapshot = tracker.poll(now + timedelta(seconds=7))
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot['started_at'], now + timedelta(seconds=1))

    def test_withdrawn_or_baseline_roll_clears_pending(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=5)
        initial = board([2, 2])
        final = board([3, 2])
        old_roll = rolls(2)
        new_roll = rolls(2, 10)

        tracker.ingest_loading(loading_args(initial, old_roll), now)
        tracker.ingest_update(update_args(final, new_roll), now + timedelta(seconds=1))
        tracker.ingest_update(update_args(final, []), now + timedelta(seconds=2))
        self.assertIsNone(tracker.poll(now + timedelta(seconds=10)))

        tracker.ingest_update(update_args(final, new_roll), now + timedelta(seconds=11))
        tracker.ingest_update(update_args(final, old_roll), now + timedelta(seconds=12))
        self.assertIsNone(tracker.poll(now + timedelta(seconds=20)))

    def test_commit_resets_start_time_for_next_round(self):
        now = datetime(2026, 9, 3, 19, 0)
        tracker = DraftTracker(stable_seconds=0)
        old_roll = rolls(2)
        first_roll = rolls(2, 10)
        second_roll = rolls(2, 20)

        tracker.ingest_loading(loading_args(board([2, 2]), old_roll), now)
        tracker.ingest_update(
            update_args(board([3, 2]), first_roll), now + timedelta(seconds=1)
        )
        self.assertIsNotNone(tracker.poll(now + timedelta(seconds=1)))
        tracker.commit_succeeded()
        self.assertFalse(tracker.active)
        self.assertIsNone(tracker.started_at)

        second_started = now + timedelta(minutes=10)
        tracker.ingest_update(update_args(board([2, 3]), first_roll), second_started)
        tracker.ingest_update(
            update_args(board([2, 3]), second_roll), second_started + timedelta(seconds=1)
        )
        snapshot = tracker.poll(second_started + timedelta(seconds=1))
        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot['started_at'], second_started)


class DraftPickSummaryTest(unittest.TestCase):
    def test_round_average_is_readable_across_eight_and_ten_team_drafts(self):
        records = []
        for session_id, team_count, picked_round in ((1, 10, 1), (2, 8, 2)):
            for round_number in (1, 2):
                for team_index in range(team_count):
                    records.append({
                        'session_id': session_id,
                        'player_id': (
                            'picked-player'
                            if round_number == picked_round and team_index == 0
                            else f'other-{session_id}-{round_number}-{team_index}'
                        ),
                        'slot': round_number + 1,
                        'is_captain': False,
                        'team_count': team_count,
                    })
            records.append({
                'session_id': session_id,
                'player_id': 'captain-only',
                'slot': 1,
                'is_captain': True,
                'team_count': team_count,
            })

        summaries = summarize_draft_pick_records(records)

        self.assertEqual(summaries['picked-player']['average_round'], 1.5)
        self.assertEqual(summaries['picked-player']['average_overall_pick'], 9.0)
        self.assertEqual(summaries['picked-player']['pick_count'], 2)
        self.assertEqual(summaries['picked-player']['team_counts'], [8, 10])
        self.assertEqual(summaries['captain-only']['captain_count'], 2)
        self.assertEqual(summaries['captain-only']['pick_count'], 0)
        self.assertIsNone(summaries['captain-only']['average_round'])
        self.assertIsNone(summaries['captain-only']['average_overall_pick'])
        # Hidden comparison metadata uses tied-round midpoint ranks, so the
        # differing number of teams does not distort cross-session position.
        self.assertEqual(summaries['picked-player']['average_pool_position'], 0.5281)


class DraftPickQueryTest(unittest.TestCase):
    def setUp(self):
        self.database = SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
        self.models = [Player, DraftSession, DraftPlayer]
        self.bind = self.database.bind_ctx(self.models)
        self.bind.__enter__()
        self.database.create_tables(self.models)

    def tearDown(self):
        self.database.drop_tables(self.models)
        self.database.close()
        self.bind.__exit__(None, None, None)

    def test_matches_draft_steam_id_to_canonical_player(self):
        Player.create(
            player_id='canonical-player', nickname='目标选手',
            steam_id='76561198000000999',
        )
        session = DraftSession.create(
            play_day='20260903', completed_at=datetime(2026, 9, 3, 19),
            roster_fingerprint='roster-query', roll_fingerprint='roll-query',
            team_count=8, status='complete',
        )
        DraftPlayer.create(
            session=session, team_num=0, slot=2, is_captain=False,
            nickname='目标选手', steam_id='76561198000000999', needs_steam=False,
        )
        DraftPlayer.create(
            session=session, team_num=1, slot=2, is_captain=False,
            nickname='无匹配选手', needs_steam=True,
        )

        summaries = draft_pick_summaries(['20260903'], ['canonical-player'])

        self.assertEqual(summaries['canonical-player']['average_round'], 1.0)
        self.assertEqual(summaries['canonical-player']['average_overall_pick'], 1.5)
        self.assertEqual(summaries['canonical-player']['pick_count'], 1)
        self.assertEqual(summaries['canonical-player']['team_counts'], [8])


class DraftPersistenceTest(unittest.TestCase):
    def setUp(self):
        self.database = SqliteDatabase(':memory:', pragmas={'foreign_keys': 1})
        self.models = [DraftSession, DraftTeam, DraftPlayer]
        self.bind = self.database.bind_ctx(self.models)
        self.bind.__enter__()
        self.database.create_tables(self.models)
        self.db_patch = patch('baokemeng_service.db', self.database)
        self.db_patch.start()

    def tearDown(self):
        self.db_patch.stop()
        self.database.drop_tables(self.models)
        self.database.close()
        self.bind.__exit__(None, None, None)

    def snapshot(self, offset=0, completed_at=None):
        return build_final_snapshot(
            board([2, 3], middle=4),
            rolls(2, offset),
            area_count=2,
            started_at=datetime(2026, 9, 3, 18, 55),
            completed_at=completed_at or datetime(2026, 9, 3, 19, 0),
        )

    def test_persist_is_idempotent_and_public_payload_is_grouped(self):
        session, created = persist_final_draft(self.snapshot())
        duplicate, duplicate_created = persist_final_draft(self.snapshot())
        self.assertTrue(created)
        self.assertFalse(duplicate_created)
        self.assertEqual(session.id, duplicate.id)
        self.assertEqual(DraftTeam.select().count(), 2)
        self.assertEqual(DraftPlayer.select().count(), 5)

        payload = public_draft_payload()
        self.assertEqual(payload['days'], ['20260903'])
        self.assertEqual(payload['selected_session']['player_count'], 5)
        self.assertEqual(len(payload['selected_session']['groups']), 1)
        public_player = payload['selected_session']['groups'][0]['teams'][0]['players'][0]
        self.assertNotIn('steam_id', public_player)
        self.assertNotIn('site_id', public_player)

    def test_reroll_supersedes_same_roster(self):
        old, _ = persist_final_draft(self.snapshot())
        new, created = persist_final_draft(self.snapshot(offset=20))
        self.assertTrue(created)
        self.assertNotEqual(old.id, new.id)
        self.assertEqual(DraftSession.get_by_id(old.id).status, 'superseded')
        self.assertEqual(DraftSession.get_by_id(new.id).status, 'complete')

    def test_repeated_roll_is_reactivated_as_current(self):
        first, _ = persist_final_draft(self.snapshot())
        second, _ = persist_final_draft(self.snapshot(
            offset=20, completed_at=datetime(2026, 9, 3, 19, 10)
        ))
        repeated, created = persist_final_draft(self.snapshot(
            completed_at=datetime(2026, 9, 3, 19, 20)
        ))

        self.assertFalse(created)
        self.assertEqual(repeated.id, first.id)
        self.assertEqual(DraftSession.get_by_id(first.id).status, 'complete')
        self.assertEqual(DraftSession.get_by_id(second.id).status, 'superseded')
        self.assertEqual(repeated.completed_at, datetime(2026, 9, 3, 19, 20))
        self.assertEqual(public_draft_payload()['selected_session']['id'], first.id)


if __name__ == '__main__':
    unittest.main()
