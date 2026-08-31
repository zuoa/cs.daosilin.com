import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

from database import MatchPlayer as DatabaseMatchPlayer
from scheduler import _store_match, canonical_match_id, refresh_perfect_ranks


class MatchIdNormalizationTest(unittest.TestCase):
    def test_numeric_and_prefixed_ids_share_one_identity(self):
        self.assertEqual(canonical_match_id(9223339745715475470), 'PVP@9223339745715475470')
        self.assertEqual(canonical_match_id('9223339745715475470'), 'PVP@9223339745715475470')
        self.assertEqual(canonical_match_id('PVP@9223339745715475470'), 'PVP@9223339745715475470')
        self.assertEqual(canonical_match_id('pvp@9223339745715475470'), 'PVP@9223339745715475470')

    def test_non_pvp_match_ids_are_preserved(self):
        self.assertEqual(canonical_match_id('official-match-1'), 'official-match-1')
        self.assertEqual(canonical_match_id(None), '')

    @patch('scheduler.MatchPlayer')
    @patch('scheduler.Match')
    def test_store_uses_list_identity_when_detail_omits_prefix(self, match_model, match_player_model):
        match_model.get_by_match_id.return_value = None
        match_data = {
            'base': {
                'matchId': '9223339745715475470',
                'map': 'de_ancient',
                'mapEn': 'de_ancient',
                'score1': 5,
                'score2': 13,
            },
            'players': [],
        }

        stored_id = _store_match(
            match_data,
            assigned_cup_name='cs-practice-20260827',
            match_id='PVP@9223339745715475470',
        )

        self.assertEqual(stored_id, 'PVP@9223339745715475470')
        self.assertEqual(
            match_model.create.call_args.kwargs['match_id'],
            'PVP@9223339745715475470',
        )
        match_player_model.is_exist.assert_not_called()

    @patch('scheduler.Player')
    @patch('scheduler.MatchPlayer')
    @patch('scheduler.Match')
    def test_store_maps_non_demo_advanced_stats(
        self, match_model, match_player_model, player_model,
    ):
        match_model.get_by_match_id.return_value = None
        match_player_model.is_exist.return_value = False
        player_model.is_exist.return_value = True
        match_data = {
            'base': {
                'matchId': '123', 'map': 'de_mirage', 'mapEn': 'de_mirage',
                'score1': 13, 'score2': 8, 'winTeam': 1,
            },
            'players': [{
                'playerId': 'p1', 'nickName': 'One', 'team': 1,
                'tradeFragCount': 4, 'grenadeDamage': 37, 'infernoDamage': 52,
                'killMap': {'p2': 3},
            }],
        }

        _store_match(match_data, assigned_cup_name='season-one')

        saved = match_player_model.create.call_args.kwargs
        self.assertEqual(saved['trade_frag_count'], 4)
        self.assertEqual(saved['grenade_damage'], 37)
        self.assertEqual(saved['inferno_damage'], 52)
        self.assertEqual(saved['kill_map'], '{"p2": 3}')
        self.assertLessEqual(set(saved), set(DatabaseMatchPlayer._meta.fields))

    @patch('scheduler.time.sleep')
    @patch('scheduler.clear_perfect_rank_cache')
    @patch('scheduler.Config')
    @patch('scheduler.get_perfect_rank')
    @patch('scheduler.resolve_steam_id64')
    @patch('scheduler.PlayerPerfectRankHistory')
    @patch('scheduler.Player')
    def test_refresh_perfect_ranks_persists_successful_lookup(
        self, player_model, rank_history_model, resolve_steam_id, get_rank,
        config_model, clear_cache, sleep,
    ):
        player = SimpleNamespace(
            player_id='76561199039451434',
            steam_id=None,
            in_library=True,
        )
        player_model.select.return_value.order_by.return_value = [player]
        resolve_steam_id.return_value = player.player_id
        get_rank.return_value = {'score': 1513, 'level': 'B'}

        stats = refresh_perfect_ranks()

        self.assertEqual(stats, {'total': 1, 'updated': 1, 'failed': 0, 'invalid': 0})
        player_model.update.assert_called_once()
        saved = player_model.update.call_args.kwargs
        self.assertEqual(saved['perfect_score'], 1513)
        self.assertEqual(saved['perfect_level'], 'B')
        self.assertIn('perfect_rank_updated_at', saved)
        rank_history_model.create.assert_called_once_with(
            player_id=player.player_id,
            score=1513,
            level='B',
            sampled_at=saved['perfect_rank_updated_at'],
        )
        config_model.set_value.assert_any_call('perfect_rank_refresh_stats', ANY)
        clear_cache.assert_called_once_with()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
