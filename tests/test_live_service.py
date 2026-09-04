import unittest
from unittest.mock import Mock, patch

import requests

from live_service import (clear_live_status_cache, get_live_status,
                          get_live_statuses)


class LiveStatusServiceTest(unittest.TestCase):
    def setUp(self):
        clear_live_status_cache()

    @staticmethod
    def response(payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    @patch('live_service.requests.get')
    def test_douyu_live_state_is_cached(self, get):
        get.return_value = self.response({
            'error': 0,
            'data': {'room_status': '1'},
        })

        first = get_live_status('DOUYU', '123')
        second = get_live_status('DOUYU', '123')

        self.assertEqual(first['status'], 'live')
        self.assertTrue(first['supported'])
        self.assertEqual(second, first)
        get.assert_called_once()

    @patch('live_service.requests.get')
    def test_huya_replay_is_treated_as_offline(self, get):
        get.return_value = self.response({
            'status': 200,
            'data': {'liveStatus': 'REPLAY'},
        })

        result = get_live_status('HUYA', '456')

        self.assertEqual(result['status'], 'offline')

    @patch('live_service.requests.get')
    def test_bilibili_live_state_is_detected(self, get):
        get.return_value = self.response({
            'code': 0,
            'data': {'live_status': 1},
        })

        result = get_live_status('BILIBILI', '789')

        self.assertEqual(result['status'], 'live')

    @patch('live_service.requests.get')
    def test_upstream_failure_becomes_unknown(self, get):
        get.side_effect = requests.Timeout('timeout')

        result = get_live_status('DOUYU', 'timeout-room')

        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(result['supported'])

    @patch('live_service.get_live_status')
    def test_batch_checks_only_valid_configured_rooms(self, status):
        status.side_effect = lambda platform, room: {
            'platform': platform,
            'status': 'live' if room == '123' else 'offline',
            'supported': True,
        }

        result = get_live_statuses({
            'p1': 'https://www.douyu.com/123',
            'p2': 'https://www.huya.com/456',
            'invalid': 'https://example.com/room',
            'empty': '',
        })

        self.assertEqual(result['p1']['status'], 'live')
        self.assertEqual(result['p2']['status'], 'offline')
        self.assertNotIn('invalid', result)
        self.assertNotIn('empty', result)


if __name__ == '__main__':
    unittest.main()
