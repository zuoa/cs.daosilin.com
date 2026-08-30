import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from database import PlayerSeasonSummary
from player_summary_service import (build_summary_input, generate_summary,
                                    snapshot_hash)


class PlayerSummaryServiceTest(unittest.TestCase):
    def test_prompt_input_keeps_trusted_zero_and_omits_ambiguous_zero(self):
        stats = {
            'match_count': 2, 'win_count': 0, 'total_rounds': 24,
            'total_kills': 0, 'total_deaths': 10, 'total_assists': 0,
            'avg_pw_rating': 0, 'avg_adpr': 0, 'avg_kast': 0,
            'total_first_kills': 0, 'total_mvp': 0,
            'demo_data': None, 'demo_coverage': {'completed': 0, 'total': 2},
        }
        with patch('player_summary_service.MatchPlayer.get_match_exploit', return_value=stats), \
                patch('player_summary_service.MatchPlayer.get_player_map_stats', return_value=[]), \
                patch('player_summary_service.MatchPlayer.get_cup_day_set', return_value=[]), \
                patch('player_summary_service.Season.get_by_cup', return_value={'cup_alias': '测试赛季'}), \
                patch('player_summary_service._player_name', return_value='测试选手'):
            result = build_summary_input('cup', 'p1', peers=[('p1', stats)])

        performance = result['表现']
        self.assertEqual(performance['胜场'], 0)
        self.assertEqual(performance['总击杀'], 0)
        self.assertEqual(performance['总助攻'], 0)
        self.assertEqual(performance['胜率'], 0)
        self.assertEqual(performance['K/D'], 0)
        self.assertNotIn('PWR Rating', performance)
        self.assertNotIn('ADR', performance)
        self.assertNotIn('KAST', performance)
        self.assertNotIn('首杀', performance)
        self.assertNotIn('MVP 次数', performance)

    def test_demo_zeroes_are_not_sent_and_coverage_is_explicit(self):
        stats = {
            'match_count': 3, 'win_count': 2, 'total_rounds': 50,
            'total_kills': 40, 'total_deaths': 35, 'total_assists': 12,
            'demo_data': {'demo_rating': 1.1, 'total_clutches_won': 0,
                          'flash_assists': 2, 'ct_adr': 0},
            'demo_coverage': {'completed': 1, 'total': 3},
        }
        with patch('player_summary_service.MatchPlayer.get_match_exploit', return_value=stats), \
                patch('player_summary_service.MatchPlayer.get_player_map_stats', return_value=[]), \
                patch('player_summary_service.MatchPlayer.get_cup_day_set', return_value=[]), \
                patch('player_summary_service.Season.get_by_cup', return_value={}), \
                patch('player_summary_service._player_name', return_value='P1'):
            result = build_summary_input('cup', 'p1', peers=[('p1', stats)])

        demo = result['Demo 数据']
        self.assertEqual(demo['覆盖场次'], 1)
        self.assertEqual(demo['赛季总场次'], 3)
        self.assertEqual(demo['指标']['Demo Rating'], 1.1)
        self.assertEqual(demo['指标']['闪光助攻'], 2)
        self.assertNotIn('残局胜利', demo['指标'])
        self.assertNotIn('CT ADR', demo['指标'])

    @patch('player_summary_service.llm_configured', return_value=True)
    def test_deepseek_json_is_validated_and_usage_returned(self, _configured):
        payload = {
            'headline': '稳中带凶的火力手',
            'overview': '这是一段足够长的赛季总评，严格依据现有数据描述选手表现，同时保持谨慎，不对缺失指标作任何推断。' * 2,
            'strength': '有效样本里的正面贡献稳定，关键指标有明确支撑。',
            'weakness': '部分高级指标样本有限，暂时更适合作为后续观察项。',
            'style': '整体属于讲究效率与稳定性的务实型打法。',
        }
        usage = SimpleNamespace(prompt_tokens=100, completion_tokens=80, total_tokens=180)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload, ensure_ascii=False)))],
            usage=usage,
        )
        client = Mock()
        client.chat.completions.create.return_value = response
        result = generate_summary({'样本': {'比赛场次': 3}}, client=client)
        self.assertEqual(result['headline'], payload['headline'])
        self.assertEqual(result['usage']['total_tokens'], 180)
        call = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call['response_format'], {'type': 'json_object'})
        self.assertEqual(call['extra_body']['thinking']['type'], 'disabled')

    def test_hash_changes_with_input(self):
        self.assertNotEqual(snapshot_hash({'比赛': 1}), snapshot_hash({'比赛': 2}))

    def test_public_payload_keeps_last_good_content_during_refresh(self):
        row = PlayerSeasonSummary(
            player_id='p1', cup_name='cup', status='queued',
            headline='旧版标题', overview='旧版总评', strength='优势',
            weakness='观察项', style='打法', sample_info='{"比赛场次": 2}',
            source_hash='old', requested_hash='new',
        )
        payload = row.public_payload()
        self.assertEqual(payload['status'], 'completed')
        self.assertTrue(payload['refreshing'])
        self.assertTrue(payload['stale'])
        self.assertEqual(payload['sample']['比赛场次'], 2)


if __name__ == '__main__':
    unittest.main()
