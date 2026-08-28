import unittest
from types import SimpleNamespace
from unittest.mock import ANY, patch

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

    @patch('scheduler.time.sleep')
    @patch('scheduler.clear_perfect_rank_cache')
    @patch('scheduler.Config')
    @patch('scheduler.get_perfect_rank')
    @patch('scheduler.resolve_steam_id64')
    @patch('scheduler.Player')
    def test_refresh_perfect_ranks_persists_successful_lookup(
        self, player_model, resolve_steam_id, get_rank, config_model, clear_cache, sleep,
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
        config_model.set_value.assert_any_call('perfect_rank_refresh_stats', ANY)
        clear_cache.assert_called_once_with()
        sleep.assert_not_called()


if __name__ == '__main__':
    unittest.main()
