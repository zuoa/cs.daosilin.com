import unittest
from datetime import date, datetime

from peewee import BooleanField, DoubleField, FloatField, IntegerField, SqliteDatabase

from community_rating_service import community_rating_summaries, rating_payload
from config import DEMO_METRIC_VERSION
from database import (DemoAnalysis, DemoPlayerStats, MatchPlayer, Player,
                      PlayerCommunityRating, PlayerSeasonSummary, Season)
from demo_service import get_demo_player_stats
from player_identity_service import (PlayerIdentityError, bind_child_accounts,
                                     unbind_child_account)


MODELS = (Player, MatchPlayer, PlayerCommunityRating, DemoAnalysis,
          DemoPlayerStats, PlayerSeasonSummary, Season)


def create_match_player(match_id, player_id, **values):
    data = {}
    for field in MatchPlayer._meta.sorted_fields:
        if field.primary_key or field.default is not None or field.null:
            continue
        if isinstance(field, BooleanField):
            data[field.name] = False
        elif isinstance(field, IntegerField):
            data[field.name] = 0
        elif isinstance(field, (FloatField, DoubleField)):
            data[field.name] = 0.0
        else:
            data[field.name] = ''
    data.update({
        'match_id': match_id,
        'player_id': player_id,
        'nickname': player_id,
        'team': 1,
        'cup_name': 'identity-cup',
        'play_day': '20260901',
        'game_count': 10,
    })
    data.update(values)
    return MatchPlayer.create(**data)


class PlayerIdentityTest(unittest.TestCase):
    def setUp(self):
        self.database = SqliteDatabase(':memory:')
        self.bind = self.database.bind_ctx(MODELS)
        self.bind.__enter__()
        self.database.create_tables(MODELS)
        Player.create(player_id='main', nickname='主玩家', steam_id='steam-main', in_library=True)
        Player.create(player_id='child', nickname='子账号', steam_id='steam-child')
        Player.create(player_id='other', nickname='对手')

    def tearDown(self):
        self.database.drop_tables(MODELS)
        self.database.close()
        self.bind.__exit__(None, None, None)

    def test_bind_aggregates_history_and_unbind_restores_it(self):
        create_match_player('m-main', 'main', kill=10, death=5, pw_rating=1.0, win=1)
        create_match_player('m-child', 'child', kill=20, death=10, pw_rating=2.0, win=0)

        result = bind_child_accounts('main', ['child'])
        stats = MatchPlayer.get_match_exploit('identity-cup', 'main', None)

        self.assertEqual(result['child_player_ids'], ['child'])
        self.assertEqual(stats['match_count'], 2)
        self.assertEqual(stats['total_kills'], 30)
        self.assertEqual(stats['total_deaths'], 15)
        self.assertEqual(stats['avg_pw_rating'], 1.5)
        self.assertEqual(Player.find_by_external_identifier(steam_id='steam-child').player_id, 'main')

        unbind_child_account('child')
        self.assertEqual(MatchPlayer.get_match_exploit('identity-cup', 'main', None)['total_kills'], 10)
        self.assertEqual(MatchPlayer.get_match_exploit('identity-cup', 'child', None)['total_kills'], 20)

    def test_bind_promotes_parent_when_child_is_in_library(self):
        Player.update(in_library=False).where(Player.player_id == 'main').execute()
        Player.update(in_library=True).where(Player.player_id == 'child').execute()

        bind_child_accounts('main', ['child'])

        self.assertTrue(Player.get_by_id('main').in_library)
        self.assertEqual(set(Player.get_library_ids()), {'main', 'child'})

        unbind_child_account('child')
        self.assertTrue(Player.get_by_id('child').in_library)
        self.assertEqual(set(Player.get_library_ids()), {'main', 'child'})

    def test_parent_account_index_is_owned_by_migration(self):
        model_indexes = Player._meta.indexes or ()
        self.assertFalse(any(
            'parent_player_id' in fields for fields, _unique in model_indexes
        ))

    def test_same_match_conflict_blocks_binding(self):
        create_match_player('shared', 'main')
        create_match_player('shared', 'child')

        with self.assertRaises(PlayerIdentityError) as caught:
            bind_child_accounts('main', ['child'])

        self.assertEqual(caught.exception.conflict_match_ids, ['shared'])
        self.assertIsNone(Player.get_by_id('child').parent_player_id)

    def test_external_stats_return_one_canonical_player(self):
        create_match_player('m-main', 'main', kill=10, death=5, pw_rating=1.0)
        create_match_player('m-child', 'child', kill=20, death=10, pw_rating=2.0)
        bind_child_accounts('main', ['child'])

        players = MatchPlayer.get_external_player_stats(['identity-cup'])
        child_lookup = MatchPlayer.get_external_player_stats(
            ['identity-cup'], player_id='child',
        )

        self.assertEqual(len(players), 1)
        self.assertEqual(players[0]['player_id'], 'main')
        self.assertEqual(players[0]['total_kills'], 30)
        self.assertEqual(child_lookup[0]['player_id'], 'main')

    def test_demo_stats_include_completed_child_account_matches(self):
        create_match_player('m-main', 'main', kill=5, death=5)
        create_match_player('m-child', 'child', kill=6, death=6)
        for match_id, player_id, kills in (
            ('m-main', 'main', 11), ('m-child', 'child', 19),
        ):
            DemoAnalysis.create(
                match_id=match_id,
                status='completed',
                metric_version=DEMO_METRIC_VERSION,
            )
            DemoPlayerStats.create(
                match_id=match_id,
                player_id=player_id,
                rounds_total=10,
                kills=kills,
                deaths=5,
            )
        bind_child_accounts('main', ['child'])

        demo = get_demo_player_stats('identity-cup', 'main')

        self.assertEqual(demo['coverage']['completed'], 2)
        self.assertEqual(demo['coverage']['total'], 2)
        self.assertEqual(demo['effective_core']['total_kills'], 30)

    def test_kill_matchups_canonicalize_both_sides_and_hide_self(self):
        create_match_player('m-main', 'main', kill_map='{"other": 4, "child": 9}')
        create_match_player('m-child', 'child', kill_map='{"other": 3}')
        create_match_player('m-other', 'other', kill_map='{"main": 2, "child": 5}')
        bind_child_accounts('main', ['child'])

        matchups = MatchPlayer.get_player_kill_matchups('identity-cup', 'main')

        self.assertEqual(len(matchups), 1)
        self.assertEqual(matchups[0]['player_id'], 'other')
        self.assertEqual(matchups[0]['kills'], 7)
        self.assertEqual(matchups[0]['deaths'], 7)

    def test_community_votes_merge_and_latest_duplicate_wins(self):
        bind_child_accounts('main', ['child'])
        now = datetime(2026, 9, 1, 10)
        PlayerCommunityRating.create(
            player_id='child', cup_name='identity-cup', voter_hash='same',
            vote_date=date(2026, 9, 1), score=1, updated_at=now,
        )
        PlayerCommunityRating.create(
            player_id='main', cup_name='identity-cup', voter_hash='same',
            vote_date=date(2026, 9, 1), score=5,
            updated_at=datetime(2026, 9, 1, 11),
        )
        for index in range(4):
            PlayerCommunityRating.create(
                player_id='child', cup_name='identity-cup', voter_hash=f'v{index}',
                vote_date=date(2026, 9, 1), score=4,
            )

        summary = community_rating_summaries('identity-cup', ['main'])['main']
        payload = rating_payload('child', 'identity-cup', reveal=True)

        self.assertEqual(summary['total_votes'], 5)
        self.assertEqual(payload['total_votes'], 5)
        self.assertEqual(next(item for item in payload['options'] if item['score'] == 1)['count'], 0)
        self.assertEqual(next(item for item in payload['options'] if item['score'] == 5)['count'], 1)


if __name__ == '__main__':
    unittest.main()
