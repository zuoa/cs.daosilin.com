import unittest
from unittest.mock import Mock, patch

import requests

from perfect_service import (
    clear_perfect_rank_cache,
    get_perfect_rank,
    perfect_level,
    resolve_steam_id64,
    to_steam_id64,
)


class PerfectLevelTest(unittest.TestCase):
    def test_s21_rank_boundaries(self):
        cases = {
            0: '未定级',
            1000: 'D',
            1001: 'C',
            1150: 'C',
            1151: 'C+',
            1300: 'C+',
            1301: '精英 C',
            1450: '精英 C',
            1451: 'B',
            1601: 'B+',
            1751: '精英 B',
            1901: 'A',
            2051: 'A+',
            2201: '精英 A',
            2400: '精英 A',
            2401: 'S',
        }
        for score, expected in cases.items():
            with self.subTest(score=score):
                self.assertEqual(perfect_level(score), expected)

    def test_normalizes_common_steam_id_formats(self):
        self.assertEqual(to_steam_id64('76561199039451434'), '76561199039451434')
        self.assertEqual(to_steam_id64('1079185706'), '76561199039451434')
        self.assertEqual(to_steam_id64('[U:1:1079185706]'), '76561199039451434')
        self.assertIsNone(to_steam_id64('not-a-steam-id'))
        self.assertEqual(resolve_steam_id64('invalid', '1079185706'), '76561199039451434')


class PerfectRankLookupTest(unittest.TestCase):
    def setUp(self):
        clear_perfect_rank_cache()

    @patch('perfect_service.requests.post')
    def test_uses_exact_steam_id_match_and_caches_result(self, post):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            'code': 1,
            'result': [
                {'steamId': '76561198000000000', 'pvpNickName': '同名玩家', 'pvpScore': 2401},
                {'steamId': '76561199039451434', 'pvpNickName': 'Rolly', 'pvpScore': 1513},
            ],
        }
        post.return_value = response

        first = get_perfect_rank('76561199039451434')
        second = get_perfect_rank('76561199039451434')

        self.assertEqual(first['level'], 'B')
        self.assertEqual(first['score'], 1513)
        self.assertEqual(first['nickname'], 'Rolly')
        self.assertEqual(second, first)
        post.assert_called_once()

    @patch('perfect_service.requests.post')
    def test_enriches_s_rank_with_authenticated_star_count(self, post):
        search_response = Mock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            'code': 1,
            'result': [{
                'steamId': '76561199039451434',
                'pvpNickName': 'Rolly',
                'pvpScore': 2401,
            }],
        }
        detail_response = Mock()
        detail_response.raise_for_status.return_value = None
        detail_response.json.return_value = {
            'statusCode': 0,
            'data': {'pvpScore': 2401, 'stars': 28},
        }
        post.side_effect = [search_response, detail_response]

        rank = get_perfect_rank(
            '76561199039451434',
            credential={
                'steam_id': '76561198000000001',
                'access_token': 'encrypted-token-value',
            },
        )

        self.assertEqual(rank['level'], 'S')
        self.assertEqual(rank['stars'], 28)
        self.assertEqual(post.call_count, 2)
        detail_call = post.call_args_list[1]
        self.assertIn('accessToken', detail_call.kwargs['headers'])
        self.assertEqual(detail_call.kwargs['json']['toSteamId'], 76561199039451434)

    @patch('perfect_service.requests.post')
    def test_s_rank_survives_optional_star_lookup_failure(self, post):
        search_response = Mock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            'code': 1,
            'result': [{
                'steamId': '76561199039451434',
                'pvpNickName': 'Rolly',
                'pvpScore': 2401,
            }],
        }
        post.side_effect = [search_response, requests.ConnectionError('expired token')]

        rank = get_perfect_rank(
            '76561199039451434',
            credential={
                'steam_id': '76561198000000001',
                'access_token': 'expired-token-value',
            },
        )

        self.assertEqual(rank['level'], 'S')
        self.assertIsNone(rank['stars'])

    @patch('perfect_service.requests.post')
    def test_uses_latest_score_list_when_top_level_stars_are_missing(self, post):
        search_response = Mock()
        search_response.raise_for_status.return_value = None
        search_response.json.return_value = {
            'code': 1,
            'result': [{
                'steamId': '76561199039451434',
                'pvpNickName': 'Rolly',
                'pvpScore': 2401,
            }],
        }
        detail_response = Mock()
        detail_response.raise_for_status.return_value = None
        detail_response.json.return_value = {
            'statusCode': 0,
            'data': {'scoreList': [{'stars': 31}, {'stars': 30}]},
        }
        post.side_effect = [search_response, detail_response]

        rank = get_perfect_rank(
            '76561199039451434',
            credential={
                'steam_id': '76561198000000001',
                'access_token': 'encrypted-token-value',
            },
        )

        self.assertEqual(rank['stars'], 31)

    @patch('perfect_service.requests.post')
    def test_invalid_id_does_not_call_upstream(self, post):
        self.assertIsNone(get_perfect_rank('player-one'))
        post.assert_not_called()

    @patch('perfect_service.requests.post')
    def test_upstream_failure_is_non_fatal(self, post):
        post.side_effect = requests.ConnectionError('network down')
        self.assertIsNone(get_perfect_rank('76561199039451434'))


if __name__ == '__main__':
    unittest.main()
