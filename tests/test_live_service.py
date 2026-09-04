import unittest
from unittest.mock import Mock, patch

import requests

from live_service import (_get_huya_live_status, clear_live_status_cache,
                          get_live_status, get_live_statuses)


class LiveStatusServiceTest(unittest.TestCase):
    def setUp(self):
        clear_live_status_cache()

    @staticmethod
    def response(payload):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = payload
        return response

    @classmethod
    def page_response(cls, room_data):
        response = cls.response(None)
        response.text = f'<script>var TT_ROOM_DATA = {room_data};</script>'
        return response

    @patch('live_service.requests.get')
    def test_douyu_live_state_is_cached(self, get):
        get.return_value = self.response({
            'room': {'show_status': 1, 'videoLoop': 0},
        })

        first = get_live_status('DOUYU', '123')
        second = get_live_status('DOUYU', '123')

        self.assertEqual(first['status'], 'live')
        self.assertTrue(first['supported'])
        self.assertEqual(second, first)
        get.assert_called_once()

    @patch('live_service.requests.get')
    def test_douyu_video_loop_is_treated_as_offline(self, get):
        get.return_value = self.response({
            'room': {'show_status': 1, 'videoLoop': 1},
        })

        result = get_live_status('DOUYU', 'carousel-room')

        self.assertEqual(result['status'], 'offline')

    @patch('live_service.requests.get')
    def test_huya_replay_is_treated_as_offline(self, get):
        get.return_value = self.response({
            'status': 200,
            'data': {'liveStatus': 'REPLAY'},
        })

        result = get_live_status('HUYA', '456')

        self.assertEqual(result['status'], 'offline')

    @patch('live_service.requests.get')
    def test_huya_real_status_overrides_playable_room_status(self, get):
        get.return_value = self.response({
            'status': 200,
            'data': {'liveStatus': 'ON', 'realLiveStatus': 'OFF'},
        })

        result = get_live_status('HUYA', 'replay-room')

        self.assertEqual(result['status'], 'offline')

    @patch('live_service.requests.get')
    def test_huya_request_uses_browser_context(self, get):
        get.return_value = self.response({
            'status': 200,
            'data': {'realLiveStatus': 'ON'},
        })

        result = get_live_status('HUYA', '678555')

        self.assertEqual(result['status'], 'live')
        _, kwargs = get.call_args
        self.assertEqual(kwargs['params']['roomid'], '678555')
        self.assertEqual(kwargs['params']['showSecret'], '1')
        self.assertEqual(kwargs['headers']['Referer'], 'https://www.huya.com/678555')
        self.assertIn('Chrome/', kwargs['headers']['User-Agent'])
        self.assertLessEqual(kwargs['timeout'].total, 3)
        self.assertLessEqual(kwargs['timeout']._connect, 3)
        self.assertLessEqual(kwargs['timeout']._read, 8)

    @patch('live_service.requests.get')
    def test_huya_timeout_is_retried(self, get):
        get.side_effect = [
            requests.Timeout('timeout'),
            self.response({
                'status': 200,
                'data': {'realLiveStatus': 'ON'},
            }),
        ]

        result = get_live_status('HUYA', '678555')

        self.assertEqual(result['status'], 'live')
        self.assertEqual(get.call_count, 2)

    @patch('live_service.requests.get')
    def test_huya_failures_fall_back_to_room_page(self, get):
        get.side_effect = [
            requests.Timeout('first timeout'),
            requests.Timeout('second timeout'),
            self.page_response(
                '{"state":"ON","isOn":true,"isReplay":false}'
            ),
        ]

        result = get_live_status('HUYA', '678555')

        self.assertEqual(result['status'], 'live')
        self.assertEqual(get.call_count, 3)
        self.assertEqual(get.call_args.args[0], 'https://www.huya.com/678555')

    @patch('live_service.time.monotonic', side_effect=[100, 100, 104, 104])
    @patch('live_service.requests.get', side_effect=requests.Timeout('timeout'))
    def test_huya_retries_share_one_overall_deadline(self, get, monotonic):
        with self.assertRaisesRegex(ValueError, '超过总时限'):
            _get_huya_live_status('678555', timeout=3)

        self.assertEqual(get.call_count, 1)
        self.assertEqual(monotonic.call_count, 4)

    @patch('live_service.requests.get')
    def test_huya_page_fallback_treats_replay_as_offline(self, get):
        get.side_effect = [
            self.response({'status': 500, 'data': {}}),
            self.page_response(
                '{"state":"ON","isOn":true,"isReplay":true}'
            ),
        ]

        result = get_live_status('HUYA', 'replay-room')

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
    def test_bilibili_round_robin_is_treated_as_offline(self, get):
        get.return_value = self.response({
            'code': 0,
            'data': {'live_status': 2},
        })

        result = get_live_status('BILIBILI', 'carousel-room')

        self.assertEqual(result['status'], 'offline')

    @patch('live_service.requests.get')
    def test_bilibili_legacy_round_status_overrides_live_status(self, get):
        get.return_value = self.response({
            'code': 0,
            'data': {'live_status': 1, 'roundStatus': 1},
        })

        result = get_live_status('BILIBILI', 'legacy-carousel-room')

        self.assertEqual(result['status'], 'offline')

    @patch('live_service.requests.get')
    def test_upstream_failure_becomes_unknown(self, get):
        get.side_effect = requests.Timeout('timeout')

        result = get_live_status('DOUYU', 'timeout-room')

        self.assertEqual(result['status'], 'unknown')
        self.assertTrue(result['supported'])

    @patch('live_service.get_live_status')
    def test_batch_checks_only_valid_configured_rooms(self, status):
        deadlines = []

        def status_result(platform, room, **kwargs):
            deadlines.append(kwargs['deadline'])
            return {
                'platform': platform,
                'status': 'live' if room == '123' else 'offline',
                'supported': True,
            }

        status.side_effect = status_result

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
        self.assertEqual(len(set(deadlines)), 1)


if __name__ == '__main__':
    unittest.main()
