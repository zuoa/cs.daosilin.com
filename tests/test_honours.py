import unittest
import json
from types import SimpleNamespace
from unittest.mock import patch

from champion_service import opening_round_loser_teams
from honours_service import (
    HONOURS_SCHEMA_VERSION,
    _apply_draft_contrast,
    _award,
    _matchup_award,
    _matchup_records,
    _minimum_matches,
    _pair_award,
    _pair_records,
    _percentiles,
    _side_award,
    _summarize_side_stats,
    _summarize_unused_utility,
    build_season_honours,
    refresh_season_honours,
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

    def test_draft_contrast_marks_early_picks_with_low_pwr_as_popular(self):
        player = {}

        _apply_draft_contrast(player, {
            'pick_count': 3,
            'average_pool_position': 0.15,
            'average_overall_pick': 2.0,
        }, pwr_percentile=0.20, pwr_rank=9)

        self.assertAlmostEqual(player['draft_popularity_gap'], 0.65)
        self.assertEqual(player['draft_popularity_gap_sample'], 3)
        self.assertEqual(player['draft_average_pick'], 2.0)
        self.assertEqual(player['pwr_rank'], 9)
        self.assertNotIn('draft_outperformance', player)

    def test_draft_contrast_requires_two_picks(self):
        player = {}

        _apply_draft_contrast(player, {
            'pick_count': 1,
            'average_pool_position': 0.10,
            'average_overall_pick': 1.0,
        }, pwr_percentile=0.10, pwr_rank=10)

        self.assertEqual(player, {})

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

    def test_matchup_award_ranks_opposing_pairs_by_kill_difference(self):
        players = {
            'a': {'player_id': 'a', 'name': 'Alpha', 'avatar': 'a.png'},
            'b': {'player_id': 'b', 'name': 'Bravo', 'avatar': 'b.png'},
            'c': {'player_id': 'c', 'name': 'Charlie', 'avatar': 'c.png'},
        }
        rows = [
            {'match_id': 'm1', 'team': 1, 'player_id': 'a-alt',
             'kill_map': json.dumps({'b': 8, 'c': 9})},
            {'match_id': 'm1', 'team': 2, 'player_id': 'b',
             'kill_map': json.dumps({'a-alt': 2, 'c': 4})},
            {'match_id': 'm1', 'team': 2, 'player_id': 'c',
             'kill_map': json.dumps({'a-alt': 4, 'b': 2})},
        ]

        records = _matchup_records(rows, {'a-alt': 'a'}, players)
        award = _matchup_award(records, players)

        self.assertEqual(records[('a', 'b')], {'a': 8, 'b': 2})
        self.assertNotIn(('b', 'c'), records)  # Same-team kills are excluded.
        self.assertEqual(award['entries'][0]['name'], 'Alpha vs Bravo')
        self.assertEqual(award['entries'][0]['display_value'], '+6 击杀差')
        self.assertEqual(award['entries'][0]['evidence'], '对位 8:2 · 共 10 次交手')
        self.assertEqual(award['entries'][1]['name'], 'Alpha vs Charlie')
        self.assertEqual(award['entries'][1]['display_value'], '+5 击杀差')
        self.assertEqual(
            [member['player_id'] for member in award['entries'][0]['members']],
            ['a', 'b'],
        )

    def test_matchup_award_requires_six_total_encounters(self):
        players = {
            'a': {'player_id': 'a', 'name': 'Alpha', 'avatar': ''},
            'b': {'player_id': 'b', 'name': 'Bravo', 'avatar': ''},
        }

        award = _matchup_award({('a', 'b'): {'a': 5}}, players)

        self.assertEqual(award['status'], 'collecting')
        self.assertEqual(award['entries'], [])

    def test_unused_utility_uses_completed_demo_rows_per_canonical_player(self):
        players = {
            'a': {'player_id': 'a', 'name': 'Alpha'},
            'b': {'player_id': 'b', 'name': 'Bravo'},
        }
        rows = [
            {'match_id': 'm1', 'player_id': 'a-alt', 'unused_utility_value': 500},
            {'match_id': 'm2', 'player_id': 'a', 'unused_utility_value': 700},
            {'match_id': 'm1', 'player_id': 'b', 'unused_utility_value': 300},
            {'match_id': 'm3', 'player_id': 'outsider', 'unused_utility_value': 900},
        ]

        result = _summarize_unused_utility(rows, {'a-alt': 'a'}, players)

        self.assertEqual(result['a'], {'total': 1200.0, 'matches': 2, 'average': 600.0})
        self.assertEqual(result['b'], {'total': 300.0, 'matches': 1, 'average': 300.0})
        self.assertNotIn('outsider', result)

    def test_side_awards_use_canonical_demo_totals_and_sample_thresholds(self):
        players = {
            'a': {'player_id': 'a', 'name': 'Alpha', 'avg_pw_rating': 1.1},
            'b': {'player_id': 'b', 'name': 'Bravo', 'avg_pw_rating': 1.2},
        }
        rows = [
            {
                'match_id': 'm1', 'player_id': 'a-alt',
                'rounds_ct': 16, 'rounds_t': 14,
                'ct_kills': 12, 't_kills': 11,
                'ct_damage': 1280, 't_damage': 1260,
                'ct_kast_rounds': 12, 't_kast_rounds': 10,
            },
            {
                'match_id': 'm2', 'player_id': 'a',
                'ct_rounds': 14, 't_rounds': 16,
                'ct_kills': 10, 't_kills': 13,
                'ct_damage': 980, 't_damage': 1600,
                'ct_kast_rounds': 11, 't_kast_rounds': 12,
            },
            {
                'match_id': 'm1', 'player_id': 'b',
                'ct_rounds': 30, 't_rounds': 30,
                'ct_kills': 20, 't_kills': 18,
                'ct_damage': 2100, 't_damage': 2400,
                'ct_kast_rounds': 21, 't_kast_rounds': 22,
            },
        ]

        side_stats = _summarize_side_stats(rows, {'a-alt': 'a'}, players)
        for player_id, stats in side_stats.items():
            players[player_id].update(stats)
        ct_award = _side_award(
            key='best-ct', title='CT', description='CT', players=players,
            side_stats=side_stats, side='ct',
        )
        t_award = _side_award(
            key='best-t', title='T', description='T', players=players,
            side_stats=side_stats, side='t',
        )

        self.assertEqual(side_stats['a']['demo_match_count'], 2)
        self.assertEqual(side_stats['a']['ct_rounds'], 30)
        self.assertEqual(ct_award['entries'][0]['player_id'], 'a')
        self.assertEqual(ct_award['entries'][0]['display_value'], '76.7% KAST')
        self.assertEqual(t_award['entries'][0]['player_id'], 'a')
        self.assertEqual(t_award['entries'][0]['display_value'], '95.3 ADR')

    def test_side_award_requests_data_when_no_demo_rounds_exist(self):
        award = _side_award(
            key='best-ct', title='CT', description='CT',
            players={}, side_stats={}, side='ct',
        )

        self.assertEqual(award['status'], 'data_required')
        self.assertEqual(award['entries'], [])

    @patch('honours_service._with_manual_awards', side_effect=lambda payload, _cup: payload)
    @patch('honours_service._calculate_season_honours')
    @patch('honours_service.SeasonHonourSnapshot.get_or_none')
    def test_public_honours_reuses_the_persisted_snapshot(self, get_snapshot, calculate, _merge):
        get_snapshot.return_value = SimpleNamespace(payload_json=json.dumps({
            'schema_version': HONOURS_SCHEMA_VERSION,
            'cup': 'cached-cup', 'awards': [], 'categories': [],
        }))

        payload = build_season_honours('cached-cup')

        self.assertEqual(payload['cup'], 'cached-cup')
        calculate.assert_not_called()

    @patch('honours_service._with_manual_awards', side_effect=lambda payload, _cup: payload)
    @patch('honours_service.refresh_season_honours')
    @patch('honours_service.SeasonHonourSnapshot.get_or_none')
    def test_public_honours_refreshes_an_old_snapshot_schema(self, get_snapshot, refresh, _merge):
        get_snapshot.return_value = SimpleNamespace(payload_json=json.dumps({
            'cup': 'stale-cup', 'awards': [], 'categories': [],
        }))
        refresh.return_value = {
            'schema_version': HONOURS_SCHEMA_VERSION,
            'cup': 'stale-cup',
            'awards': [],
            'categories': [],
        }

        payload = build_season_honours('stale-cup')

        self.assertEqual(payload['schema_version'], HONOURS_SCHEMA_VERSION)
        refresh.assert_called_once_with('stale-cup', include_archived=True)

    @patch('honours_service._calculate_season_honours')
    @patch('honours_service.SeasonHonourSnapshot.get_or_none')
    @patch('honours_service.Season.get_by_cup', return_value={'status': 'archived'})
    def test_archived_snapshot_is_never_recalculated(self, _season, get_snapshot, calculate):
        get_snapshot.return_value = SimpleNamespace(payload_json=json.dumps({
            'cup': 'sealed-cup', 'status': 'final',
        }))

        payload = refresh_season_honours('sealed-cup')

        self.assertEqual(payload['status'], 'final')
        calculate.assert_not_called()

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
        self.assertIn('must-revalidate', response.headers['Cache-Control'])

    @patch('app.invalidate_season')
    @patch('app.save_manual_honour')
    @patch('app.current_admin', return_value='admin')
    def test_admin_can_create_a_manual_honour(self, _admin, save_honour, invalidate):
        from app import app

        save_honour.return_value = {'id': 7, 'title': '关键局定心丸'}
        response = app.test_client().post('/api/admin/honours', json={
            'cup': 'manual-cup',
            'title': '关键局定心丸',
            'description': '关键时刻稳住全队。',
            'recipients': [{'player_id': 'p1', 'reason': '决赛连续完成残局。'}],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['id'], 7)
        save_honour.assert_called_once()
        invalidate.assert_called_once_with('manual-cup', external=False)


if __name__ == '__main__':
    unittest.main()
