import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from season_lineup_service import (
    LineupValidationError,
    SYSTEM_PROMPT,
    _ensure_snapshot_feasible,
    aggregate_ballots,
    generate_ballot,
    validate_ballot,
)


FUNCTIONS = ('opener', 'support', 'closer', 'flex', 'flex')


def snapshot(count=12):
    candidates = []
    for index in range(count):
        candidates.append({
            'player_id': f'p{index:02d}',
            'player_name': f'Player {index:02d}',
            'avatar': '',
            'metrics': {
                'pwr_rating': round(1.4 - index / 100, 2),
                'match_count': 10,
                'win_rate': round(.7 - index / 100, 2),
            },
            'demo_coverage': {'completed': 5, 'total': 10, 'ratio': .5},
            'allowed_weapon_roles': (
                ['awper', 'rifler'] if index in (0, 5, 10) else ['rifler']
            ),
            'allowed_function_roles': ['opener', 'support', 'closer', 'flex'],
        })
    return {
        'season': {'cup_name': 's1', 'data_cutoff': '2026-09-10T12:00:00'},
        'eligibility': {'minimum_matches': 5, 'candidate_count': count},
        'candidates': candidates,
    }


def member(player_id, offset):
    return {
        'player_id': player_id,
        'weapon_role': 'awper' if offset == 0 else 'rifler',
        'function_role': FUNCTIONS[offset],
        'reason': '在本赛季的个人输出与胜利成果之间取得了稳定平衡。',
        'evidence': ['pwr_rating', 'win_rate'],
    }


def ballot(first=0, second=5, index=1, perspective='individual'):
    return {
        'first_team': [member(f'p{first + offset:02d}', offset) for offset in range(5)],
        'second_team': [member(f'p{second + offset:02d}', offset) for offset in range(5)],
        'ballot_index': index,
        'perspective': perspective,
    }


class SeasonLineupTest(unittest.TestCase):
    def test_prompt_forbids_igl_inference_and_locks_balanced_weight(self):
        self.assertIn('IGL', SYSTEM_PROMPT)
        self.assertIn('50%', SYSTEM_PROMPT)
        self.assertIn('10 人不得重复', SYSTEM_PROMPT)

    def test_snapshot_requires_ten_candidates(self):
        with self.assertRaisesRegex(LineupValidationError, '至少需要 10 人'):
            _ensure_snapshot_feasible(snapshot(9))

    def test_snapshot_requires_two_evidence_backed_awpers(self):
        value = snapshot()
        for candidate in value['candidates']:
            candidate['allowed_weapon_roles'] = ['rifler']
        value['candidates'][0]['allowed_weapon_roles'] = ['awper', 'rifler']

        with self.assertRaisesRegex(LineupValidationError, '两名.*主狙'):
            _ensure_snapshot_feasible(value)

    def test_valid_ballot_is_normalized(self):
        value = ballot()
        value.pop('ballot_index')
        value.pop('perspective')

        result = validate_ballot(value, snapshot())

        self.assertEqual(len(result['first_team']), 5)
        self.assertEqual(result['first_team'][0]['weapon_role'], 'awper')

    @patch('season_lineup_service.llm_configured', return_value=True)
    def test_generate_ballot_uses_json_mode_and_validates_response(self, _configured):
        value = ballot()
        value.pop('ballot_index')
        value.pop('perspective')
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(
                content=__import__('json').dumps(value, ensure_ascii=False),
            ))],
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=200, total_tokens=300),
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: response,
        )))

        result, usage = generate_ballot(snapshot(), 'fit', 3, client=client)

        self.assertEqual(result['perspective'], 'fit')
        self.assertEqual(result['ballot_index'], 3)
        self.assertEqual(usage['total_tokens'], 300)

    def test_ballot_rejects_cross_team_duplicates(self):
        value = ballot()
        value.pop('ballot_index')
        value.pop('perspective')
        value['second_team'][4]['player_id'] = 'p01'

        with self.assertRaisesRegex(LineupValidationError, '重复选手'):
            validate_ballot(value, snapshot())

    def test_ballot_rejects_unsupported_awper_assignment(self):
        value = ballot()
        value.pop('ballot_index')
        value.pop('perspective')
        value['first_team'][0]['weapon_role'] = 'rifler'
        value['first_team'][1]['weapon_role'] = 'awper'

        with self.assertRaisesRegex(LineupValidationError, '没有数据支持'):
            validate_ballot(value, snapshot())

    def test_aggregation_keeps_consensus_and_hard_constraints(self):
        ballots = []
        themes = ('individual', 'winning', 'fit')
        for index in range(21):
            ballots.append(ballot(index=index + 1, perspective=themes[index % 3]))

        result = aggregate_ballots(ballots, snapshot())

        first_ids = {member['player_id'] for member in result['first_team']}
        second_ids = {member['player_id'] for member in result['second_team']}
        self.assertEqual(first_ids, {f'p{index:02d}' for index in range(5)})
        self.assertEqual(second_ids, {f'p{index:02d}' for index in range(5, 10)})
        self.assertFalse(first_ids & second_ids)
        for key in ('first_team', 'second_team'):
            team = result[key]
            self.assertEqual(sum(member['weapon_role'] == 'awper' for member in team), 1)
            self.assertTrue({'opener', 'support', 'closer'}.issubset(
                {member['function_role'] for member in team}
            ))
            self.assertTrue(all(member['selection_rate'] == 1 for member in team))

    def test_aggregation_repairs_mixed_ballots_globally(self):
        ballots = []
        for index in range(21):
            value = ballot(index=index + 1, perspective='fit')
            if index >= 11:
                value = copy.deepcopy(value)
                value['first_team'][4], value['second_team'][4] = (
                    value['second_team'][4], value['first_team'][4]
                )
            ballots.append(value)

        result = aggregate_ballots(ballots, snapshot())
        ids = [member['player_id'] for key in ('first_team', 'second_team')
               for member in result[key]]

        self.assertEqual(len(ids), 10)
        self.assertEqual(len(set(ids)), 10)


if __name__ == '__main__':
    unittest.main()
