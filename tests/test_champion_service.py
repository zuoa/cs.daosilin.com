import unittest
from unittest.mock import patch

from champion_service import (_player_ids_by_team, _resolved_team_key,
                              _team_aliases_from_players,
                              calculate_daily_podium, judge_champion)


def add_bo3(matches, team1, team2, winners, start_index=None):
    """Append a BO3, swapping sides on every second map like real records."""
    start_index = start_index or len(matches) + 1
    for offset, winner in enumerate(winners):
        left, right = (team1, team2) if offset % 2 == 0 else (team2, team1)
        matches.append({
            'match_id': f'PVP@{start_index + offset}',
            'team1_name': left,
            'team2_name': right,
            'team1_score': 13 if winner == left else 8,
            'team2_score': 13 if winner == right else 8,
            'end_time': f'2026-09-03 {17 + start_index // 20:02d}:{start_index % 60:02d}:{offset:02d}',
        })


def full_day_matches():
    matches = []
    # First round: A, C, E and G become 1-0.
    add_bo3(matches, 'A', 'B', ['A', 'A'])
    add_bo3(matches, 'C', 'D', ['D', 'C', 'C'])
    add_bo3(matches, 'E', 'F', ['E', 'E'])
    add_bo3(matches, 'G', 'H', ['G', 'H', 'G'])
    # Second round: equal-record opponents meet. A and E become 2-0.
    add_bo3(matches, 'A', 'C', ['C', 'A', 'A'])
    add_bo3(matches, 'E', 'G', ['E', 'E'])
    add_bo3(matches, 'B', 'D', ['B', 'B'])
    add_bo3(matches, 'F', 'H', ['H', 'F', 'F'])
    # Final: E wins 2-1 over A.
    add_bo3(matches, 'A', 'E', ['A', 'E', 'E'])
    return matches


def renamed_team_day():
    """Return a full day where two teams change display names between rounds."""
    matches = full_day_matches()
    for match in matches:
        for field in ('team1_name', 'team2_name'):
            if match[field] == 'C':
                match[field] = 'LZK队'
            elif match[field] == 'E':
                match[field] = '小秋队'

    # These are the two name changes observed in the 2026-09-04 matches.
    for match in matches[10:13]:
        for field in ('team1_name', 'team2_name'):
            if match[field] == 'LZK队':
                match[field] = 'LZK'
    for match in matches[20:]:
        for field in ('team1_name', 'team2_name'):
            if match[field] == '小秋队':
                match[field] = '活力小秋队'

    canonical_names = {'LZK': 'LZK队', '活力小秋队': '小秋队'}
    players = []
    for match in matches:
        for team_name in (match['team1_name'], match['team2_name']):
            canonical = canonical_names.get(team_name, team_name)
            players.extend({
                'team_name': team_name,
                'player_id': f'{canonical}-player-{index}',
            } for index in range(5))
    return matches, players


class DailyPodiumCalculationTest(unittest.TestCase):
    def test_resolves_two_zero_teams_and_final_bo3(self):
        podium = calculate_daily_podium(full_day_matches())

        self.assertEqual(podium['champion_team'], 'E')
        self.assertEqual(podium['runner_up_team'], 'A')
        self.assertEqual(podium['final_score'], (2, 1))

    def test_ignores_duplicate_wmpvp_id_forms(self):
        matches = full_day_matches()
        duplicate = dict(matches[0])
        duplicate['match_id'] = duplicate['match_id'].removeprefix('PVP@')
        matches.insert(1, duplicate)

        podium = calculate_daily_podium(matches)

        self.assertEqual(podium['champion_team'], 'E')
        self.assertEqual(podium['runner_up_team'], 'A')

    def test_does_not_publish_before_final_is_complete(self):
        matches = full_day_matches()
        self.assertIsNone(calculate_daily_podium(matches[:-1]))

    def test_rejects_second_round_pairing_with_different_records(self):
        matches = full_day_matches()
        second_round_start = sum((2, 3, 2, 3))
        for match in matches[second_round_start:second_round_start + 3]:
            if match['team1_name'] == 'C':
                match['team1_name'] = 'B'
            if match['team2_name'] == 'C':
                match['team2_name'] = 'B'
        self.assertIsNone(calculate_daily_podium(matches))

    def test_resolves_team_renames_from_stable_rosters(self):
        matches, players = renamed_team_day()
        self.assertIsNone(calculate_daily_podium(matches))

        aliases, renamed_groups = _team_aliases_from_players(players)
        podium = calculate_daily_podium(matches, aliases)

        self.assertCountEqual(
            renamed_groups,
            [['LZK队', 'LZK'], ['小秋队', '活力小秋队']],
        )
        self.assertEqual(podium['champion_team'], '活力小秋队')
        self.assertEqual(podium['runner_up_team'], 'A')
        player_ids = _player_ids_by_team(players, aliases)
        champion_key = _resolved_team_key(podium['champion_team'], aliases)
        self.assertEqual(
            set(player_ids[champion_key].split(',')),
            {f'小秋队-player-{index}' for index in range(5)},
        )

    def test_does_not_merge_teams_with_only_one_shared_player(self):
        players = [
            *({'team_name': 'A', 'player_id': f'a-{index}'} for index in range(5)),
            {'team_name': 'B', 'player_id': 'a-0'},
            *({'team_name': 'B', 'player_id': f'b-{index}'} for index in range(4)),
        ]

        aliases, renamed_groups = _team_aliases_from_players(players)

        self.assertNotEqual(aliases['a'], aliases['b'])
        self.assertEqual(renamed_groups, [])


class ChampionPersistenceTest(unittest.TestCase):
    @patch('champion_service.invalidate_season')
    @patch('champion_service.CupDayChampion')
    @patch('champion_service.MatchPlayer')
    @patch('champion_service.Match')
    def test_persists_teams_and_raw_match_account_ids(
        self, match_model, match_player_model, champion_model, invalidate,
    ):
        matches = full_day_matches()
        for match in matches:
            if match['team1_name'] == 'E':
                match['team1_name'] = 'Team  E'
            if match['team2_name'] == 'E':
                match['team2_name'] = 'Team  E'
        match_model.filter_records.return_value = matches

        match_player_model.filter_records.return_value = [
            {'team_name': ' team   e ', 'player_id': 'winner-child'},
            {'team_name': 'TEAM E', 'player_id': 'winner-child'},
            {'team_name': 'a', 'player_id': 'runner-child'},
        ]
        champion_model.is_exist.return_value = False

        result = judge_champion(day='20260903', cup_name='identity-cup')

        saved = champion_model.create.call_args.kwargs
        self.assertEqual(result['champion_team'], 'Team E')
        self.assertEqual(saved['champion_team_name'], 'Team E')
        self.assertEqual(saved['runner_up_team_name'], 'A')
        self.assertEqual(saved['champion_team_player_ids'], 'winner-child')
        self.assertEqual(saved['runner_up_team_player_ids'], 'runner-child')
        match_player_model.filter_records.assert_called_once_with(
            cup_name='identity-cup', play_day='20260903',
        )
        invalidate.assert_called_once_with('identity-cup', external=False)

    @patch('champion_service.invalidate_season')
    @patch('champion_service.CupDayChampion')
    @patch('champion_service.MatchPlayer')
    @patch('champion_service.Match')
    def test_corrects_an_existing_stale_runner_up(
        self, match_model, match_player_model, champion_model, invalidate,
    ):
        match_model.filter_records.return_value = full_day_matches()
        match_player_model.filter_records.return_value = []
        champion_model.is_exist.return_value = True
        champion_model.get_champion_by_cup_and_day.return_value = {
            'cup_name': 'identity-cup',
            'day': '20260903',
            'champion_team_name': 'E',
            'runner_up_team_name': 'wrong-team',
            'champion_team_player_ids': '',
            'runner_up_team_player_ids': '',
        }

        judge_champion(day='20260903', cup_name='identity-cup')

        updates = champion_model.update.call_args.kwargs
        self.assertEqual(updates['champion_team_name'], 'E')
        self.assertEqual(updates['runner_up_team_name'], 'A')
        champion_model.create.assert_not_called()
        invalidate.assert_called_once_with('identity-cup', external=False)

    @patch('champion_service.invalidate_season')
    @patch('champion_service.CupDayChampion')
    @patch('champion_service.MatchPlayer')
    @patch('champion_service.Match')
    def test_incomplete_day_is_not_saved(
        self, match_model, match_player_model, champion_model, invalidate,
    ):
        match_model.filter_records.return_value = full_day_matches()[:-1]

        result = judge_champion(day='20260903', cup_name='identity-cup')

        self.assertIsNone(result)
        champion_model.create.assert_not_called()
        match_player_model.filter_records.assert_called_once_with(
            cup_name='identity-cup', play_day='20260903',
        )
        invalidate.assert_not_called()

    @patch('champion_service.invalidate_season')
    @patch('champion_service.CupDayChampion')
    @patch('champion_service.MatchPlayer')
    @patch('champion_service.Match')
    def test_persists_podium_when_teams_are_renamed_between_rounds(
        self, match_model, match_player_model, champion_model, invalidate,
    ):
        matches, players = renamed_team_day()
        match_model.filter_records.return_value = matches
        match_player_model.filter_records.return_value = players
        champion_model.is_exist.return_value = False

        result = judge_champion(day='20260903', cup_name='rename-cup')

        self.assertEqual(result['champion_team'], '活力小秋队')
        self.assertEqual(result['runner_up_team'], 'A')
        saved = champion_model.create.call_args.kwargs
        self.assertEqual(saved['champion_team_name'], '活力小秋队')
        self.assertEqual(
            set(saved['champion_team_player_ids'].split(',')),
            {f'小秋队-player-{index}' for index in range(5)},
        )
        invalidate.assert_called_once_with('rename-cup', external=False)


if __name__ == '__main__':
    unittest.main()
