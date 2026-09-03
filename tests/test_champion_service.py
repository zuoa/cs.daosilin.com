import unittest
from unittest.mock import patch

from champion_service import judge_champion


class ChampionAccountAttributionTest(unittest.TestCase):
    @patch('champion_service.invalidate_season')
    @patch('champion_service.CupDayChampion')
    @patch('champion_service.MatchPlayer')
    @patch('champion_service.Match')
    def test_judgment_persists_raw_match_account_ids(
        self, match_model, match_player_model, champion_model, invalidate,
    ):
        match_model.filter_records.return_value = [
            {
                'team1_name': 'Winner', 'team2_name': opponent,
                'team1_score': 13, 'team2_score': 5,
                'end_time': round_number * 100 + game_number,
            }
            for round_number, opponent in enumerate(('Team B', 'Team C', 'Runner'), 1)
            for game_number in (1, 2)
        ]

        def players_for_team(**filters):
            if filters['team_name'] == 'Winner':
                return [{'player_id': 'bound-child'}]
            if filters['team_name'] == 'Runner':
                return [{'player_id': 'runner-child'}]
            return []

        match_player_model.filter_records.side_effect = players_for_team
        champion_model.is_exist.return_value = False

        judge_champion(day='20260903', cup_name='identity-cup')

        saved = champion_model.create.call_args.kwargs
        self.assertEqual(saved['champion_team_player_ids'], 'bound-child')
        self.assertEqual(saved['runner_up_team_player_ids'], 'runner-child')
        invalidate.assert_called_once_with('identity-cup', external=False)


if __name__ == '__main__':
    unittest.main()
