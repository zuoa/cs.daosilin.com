import unittest
from unittest.mock import patch

from champion_service import opening_round_loser_teams
from honours_service import (
    _award,
    _minimum_matches,
    _pair_award,
    _pair_records,
    _percentiles,
)


def add_bo3(matches, left, right, winner):
    for index in range(2):
        matches.append({
            'match_id': f'{left}-{right}-{index}',
            'team1_name': left,
            'team2_name': right,
            'team1_score': 13 if winner == left else 8,
            'team2_score': 13 if winner == right else 8,
            'end_time': f'2026-09-09 20:0{len(matches)}:00',
        })


class HonourCalculationTest(unittest.TestCase):
    def test_percentiles_use_average_rank_for_ties(self):
        result = _percentiles({'a': 10, 'b': 20, 'c': 20, 'd': 40})

        self.assertEqual(result['a'], 0)
        self.assertEqual(result['d'], 1)
        self.assertAlmostEqual(result['b'], 0.5)
        self.assertEqual(result['b'], result['c'])

    def test_match_threshold_tracks_thirty_percent_of_the_leader(self):
        self.assertEqual(_minimum_matches({'a': {'match_count': 3}}), 1)
        self.assertEqual(_minimum_matches({'a': {'match_count': 10}}), 3)
        self.assertEqual(_minimum_matches({'a': {'match_count': 21}}), 7)

    def test_award_is_deterministic_and_marks_tied_values(self):
        players = {
            'b': {'player_id': 'b', 'name': 'Bravo', 'score': 5, 'score_sample': 4, 'avg_pw_rating': 1.2},
            'a': {'player_id': 'a', 'name': 'Alpha', 'score': 5, 'score_sample': 6, 'avg_pw_rating': 1.1},
            'c': {'player_id': 'c', 'name': 'Charlie', 'score': 4, 'score_sample': 9, 'avg_pw_rating': 1.8},
            'd': {'player_id': 'd', 'name': 'Delta', 'score': 3, 'score_sample': 9, 'avg_pw_rating': 1.9},
        }

        award = _award(
            key='sample', category='match', title='示例', description='示例',
            method='按分数排名。', players=players, metric='score',
            eligible=lambda _player: True,
            display=lambda player: str(player['score']),
            evidence=lambda player: f"样本 {player['score_sample']}",
        )

        self.assertEqual([entry['player_id'] for entry in award['entries']], ['a', 'b', 'c'])
        self.assertTrue(award['entries'][0]['tied'])
        self.assertTrue(award['entries'][1]['tied'])
        self.assertFalse(award['entries'][2]['tied'])

    def test_opening_round_losers_are_read_from_completed_bo3s(self):
        matches = []
        add_bo3(matches, 'Alpha', 'Bravo', 'Alpha')
        add_bo3(matches, 'Charlie', 'Delta', 'Delta')

        self.assertEqual(opening_round_loser_teams(matches), {'bravo', 'charlie'})

    def test_pair_award_counts_same_team_maps_and_ranks_lowest_win_rate(self):
        players = {
            'a': {'player_id': 'a', 'name': 'Alpha', 'avatar': 'a.png'},
            'b': {'player_id': 'b', 'name': 'Bravo', 'avatar': 'b.png'},
            'c': {'player_id': 'c', 'name': 'Charlie', 'avatar': 'c.png'},
        }
        rows = []
        for match_id, winner in [('m1', True), ('m2', False), ('m3', False)]:
            rows.extend([
                {'match_id': match_id, 'team': 1, 'player_id': 'a-alt', 'win': int(winner)},
                {'match_id': match_id, 'team': 1, 'player_id': 'b', 'win': int(winner)},
            ])
        for match_id in ('m4', 'm5', 'm6'):
            rows.extend([
                {'match_id': match_id, 'team': 2, 'player_id': 'a', 'win': 1},
                {'match_id': match_id, 'team': 2, 'player_id': 'c', 'win': 1},
            ])

        records = _pair_records(rows, {'a-alt': 'a'}, players)
        award = _pair_award(
            key='duo-slump', title='相遇即低谷', description='示例', method='示例',
            pair_records=records, players=players, minimum_maps=3, lowest=True,
        )

        self.assertEqual(award['entries'][0]['name'], 'Alpha × Bravo')
        self.assertEqual(award['entries'][0]['display_value'], '33.3% 胜率')
        self.assertEqual(award['entries'][0]['members'][0]['player_id'], 'a')
        self.assertEqual(award['entries'][1]['name'], 'Alpha × Charlie')

    @patch('app.build_season_honours')
    def test_public_api_exposes_the_honours_payload(self, build_honours):
        from app import app

        build_honours.return_value = {
            'cup': 'honours-api-test',
            'cup_alias': '接口测试赛季',
            'status': 'provisional',
            'generated_at': '2026-09-09T12:00:00',
            'eligible_player_count': 3,
            'minimum_matches': 2,
            'available_award_count': 1,
            'categories': [{'key': 'podium', 'label': '领奖台常客'}],
            'awards': [{'key': 'champion-counter', 'entries': []}],
        }

        response = app.test_client().get('/api/v1/cup/honours-api-test/honours')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['cup'], 'honours-api-test')
        self.assertIn('stale-while-revalidate', response.headers['Cache-Control'])


if __name__ == '__main__':
    unittest.main()
