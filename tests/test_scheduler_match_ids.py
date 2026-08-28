import unittest
from unittest.mock import patch

from scheduler import _store_match, canonical_match_id


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


if __name__ == '__main__':
    unittest.main()
