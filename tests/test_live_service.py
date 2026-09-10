import unittest
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import requests

from live_service import (_HuyaStatusObservation, _get_huya_live_status,
                          _parse_huya_mobile_page_status,
                          clear_live_status_cache, get_cached_live_statuses,
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
    def test_cached_batch_does_not_query_and_defaults_to_offline(self, get):
        result = get_cached_live_statuses({
            'p1': 'https://www.douyu.com/not-yet-refreshed',
            'invalid': 'https://example.com/room',
        })

        self.assertEqual(result['p1']['status'], 'offline')
        self.assertEqual(result['invalid']['status'], 'offline')
        get.assert_not_called()

    @patch('live_service.requests.get')
    def test_forced_refresh_replaces_unexpired_status(self, get):
        get.side_effect = [
            self.response({'room': {'show_status': 2, 'videoLoop': 0}}),
            self.response({'room': {'show_status': 1, 'videoLoop': 0}}),
        ]

        first = get_live_status('DOUYU', 'forced-room')
        refreshed = get_live_status('DOUYU', 'forced-room', force_refresh=True)
        cached = get_cached_live_statuses({
            'p1': 'https://www.douyu.com/forced-room',
        })

        self.assertEqual(first['status'], 'offline')
        self.assertEqual(refreshed['status'], 'live')
        self.assertEqual(cached['p1']['status'], 'live')
        self.assertEqual(get.call_count, 2)

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
    def test_huya_timeout_hedges_to_desktop_and_mobile_without_retrying_json(self, get):
        requested_urls = []

        def response_for(url, **kwargs):
            requested_urls.append(url)
            if url == 'https://mp.huya.com/cache.php':
                raise requests.Timeout('timeout')
            if url == 'https://www.huya.com/678555':
                return self.page_response('{"state":"ON","isReplay":false}')
            response = self.response(None)
            response.text = '<html>no mobile room data</html>'
            return response

        get.side_effect = response_for

        result = get_live_status('HUYA', '678555')

        self.assertEqual(result['status'], 'live')
        self.assertEqual(requested_urls.count('https://mp.huya.com/cache.php'), 1)
        self.assertCountEqual(requested_urls, [
            'https://mp.huya.com/cache.php',
            'https://www.huya.com/678555',
            'https://m.huya.com/678555',
        ])

    @patch('live_service.requests.get')
    def test_huya_failures_can_fall_back_to_mobile_page(self, get):
        def response_for(url, **kwargs):
            if url == 'https://mp.huya.com/cache.php':
                raise requests.Timeout('profile timeout')
            if url == 'https://www.huya.com/678555':
                raise requests.Timeout('desktop timeout')
            response = self.response(None)
            response.text = (
                '<script>window.HNF_GLOBAL_INIT = '
                '{"roomInfo":{"eLiveStatus":2,"tReplayInfo":{"lUid":0}}};'
                '</script>'
            )
            return response

        get.side_effect = response_for

        result = get_live_status('HUYA', '678555')

        self.assertEqual(result['status'], 'live')
        self.assertEqual(get.call_count, 3)

    @patch('live_service.HUYA_FALLBACK_HEDGE_SECONDS', 0.01)
    @patch('live_service._fetch_huya_mobile_status')
    @patch('live_service._fetch_huya_desktop_status')
    @patch('live_service._fetch_huya_profile_status')
    def test_huya_slow_json_starts_page_sources_together(self, profile, desktop, mobile):
        starts = {}

        def slow_profile(room_id, deadline):
            time.sleep(0.03)
            raise requests.Timeout('profile timeout')

        def page_result(source, status):
            def fetch(room_id, deadline):
                starts[source] = time.monotonic()
                return [_HuyaStatusObservation(status, source)]
            return fetch

        profile.side_effect = slow_profile
        desktop.side_effect = page_result('desktop', 'offline')
        mobile.side_effect = page_result('mobile', 'live')

        result = _get_huya_live_status('678555', timeout=0.2)

        self.assertEqual(result, 'live')
        self.assertLess(abs(starts['desktop'] - starts['mobile']), 0.05)
        profile.assert_called_once()
        desktop.assert_called_once()
        mobile.assert_called_once()

    @patch('live_service.requests.get')
    def test_huya_page_fallback_treats_replay_as_offline(self, get):
        def response_for(url, **kwargs):
            if url == 'https://mp.huya.com/cache.php':
                return self.response({'status': 500, 'data': {}})
            if url == 'https://www.huya.com/replay-room':
                return self.page_response(
                    '{"state":"ON","isOn":true,"isReplay":true}'
                )
            response = self.response(None)
            response.text = '<html>no mobile room data</html>'
            return response

        get.side_effect = response_for

        result = get_live_status('HUYA', 'replay-room')

        self.assertEqual(result['status'], 'offline')

    def test_huya_mobile_page_parser_handles_live_offline_and_replay(self):
        def page(status, replay_uid=0):
            return (
                '<script>window.HNF_GLOBAL_INIT = '
                f'{{"roomInfo":{{"eLiveStatus":{status},'
                f'"tReplayInfo":{{"lUid":{replay_uid}}}}}}}; </script>'
            )

        self.assertEqual(_parse_huya_mobile_page_status(page(2)), 'live')
        self.assertEqual(_parse_huya_mobile_page_status(page(1)), 'offline')
        self.assertEqual(_parse_huya_mobile_page_status(page(2, 123)), 'offline')

    @patch('live_service.HUYA_FALLBACK_HEDGE_SECONDS', 0.001)
    @patch('live_service._fetch_huya_mobile_status')
    @patch('live_service._fetch_huya_desktop_status')
    @patch('live_service._fetch_huya_profile_status')
    @patch('live_service.logger.warning')
    def test_huya_cross_source_conflict_prefers_real_live_status(
            self, warning, profile, desktop, mobile):
        def profile_result(room_id, deadline):
            time.sleep(0.01)
            return [
                _HuyaStatusObservation(
                    'offline', 'profile.realLiveStatus', real_live_status=True,
                ),
                _HuyaStatusObservation('live', 'profile.liveStatus'),
            ]

        profile.side_effect = profile_result
        desktop.return_value = [_HuyaStatusObservation('live', 'desktop')]
        mobile.return_value = [_HuyaStatusObservation('live', 'mobile')]

        self.assertEqual(_get_huya_live_status('conflict', timeout=0.2), 'offline')
        warning.assert_called_once()

    @patch('live_service.HUYA_FALLBACK_HEDGE_SECONDS', 0.001)
    @patch('live_service._fetch_huya_mobile_status')
    @patch('live_service._fetch_huya_desktop_status')
    @patch('live_service._fetch_huya_profile_status')
    def test_huya_cross_source_conflict_otherwise_prefers_live(
            self, profile, desktop, mobile):
        def profile_result(room_id, deadline):
            time.sleep(0.01)
            return [_HuyaStatusObservation('offline', 'profile.liveStatus')]

        profile.side_effect = profile_result
        desktop.return_value = [_HuyaStatusObservation('offline', 'desktop')]
        mobile.return_value = [_HuyaStatusObservation('live', 'mobile')]

        self.assertEqual(_get_huya_live_status('conflict', timeout=0.2), 'live')

    @patch('live_service.LIVE_STATUS_CACHE_SECONDS', 0)
    @patch('live_service._get_huya_live_status')
    def test_huya_all_source_failure_returns_last_good_as_stale(self, huya_status):
        huya_status.side_effect = ['live', ValueError('all sources failed')]

        fresh = get_live_status('HUYA', 'last-good')
        stale = get_live_status('HUYA', 'last-good')

        self.assertEqual(fresh['status'], 'live')
        self.assertFalse(fresh['stale'])
        self.assertEqual(stale['status'], 'live')
        self.assertTrue(stale['stale'])
        self.assertEqual(huya_status.call_count, 2)

    @patch('live_service._get_huya_live_status')
    def test_huya_overlapping_room_checks_share_one_inflight_query(self, huya_status):
        def delayed_status(*args, **kwargs):
            time.sleep(0.03)
            return 'live'

        huya_status.side_effect = delayed_status
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(get_live_status, 'HUYA', 'same-room')
                for _ in range(2)
            ]
            results = [future.result() for future in futures]

        self.assertEqual([item['status'] for item in results], ['live', 'live'])
        huya_status.assert_called_once()

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
            'p3': 'https://www.douyu.com/123',
            'invalid': 'https://example.com/room',
            'empty': '',
        })

        self.assertEqual(result['p1']['status'], 'live')
        self.assertEqual(result['p2']['status'], 'offline')
        self.assertEqual(result['p3']['status'], 'live')
        self.assertNotIn('invalid', result)
        self.assertNotIn('empty', result)
        self.assertEqual(len(set(deadlines)), 1)
        self.assertEqual(status.call_count, 2)


if __name__ == '__main__':
    unittest.main()
