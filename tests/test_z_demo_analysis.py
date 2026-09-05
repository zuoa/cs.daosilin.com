import json
import os
import shutil
import tempfile
import unittest
import bz2
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from peewee import BooleanField, DoubleField, FloatField, IntegerField

from app import app
import demo_worker
from database import (Config, DemoAnalysis, DemoCredential, DemoPlayerStats,
                      MatchPlayer, Player, create_tables, db)
from demo_service import (attach_demo_stats, demo_analysis_enabled,
                          load_demo_credential, persist_analysis,
                          save_demo_credential, set_demo_analysis_enabled)
from demo_tasks import (_demo_job_id, _extract_demo, _safe_error,
                        cleanup_demo_archives,
                        schedule_demo_analysis)
from rq.job import validate_job_id


def create_platform_row(match_id, player_id, **values):
    data = {}
    for field in MatchPlayer._meta.sorted_fields:
        if field.primary_key or field.default is not None or field.null:
            continue
        if isinstance(field, BooleanField):
            data[field.name] = False
        elif isinstance(field, IntegerField):
            data[field.name] = 0
        elif isinstance(field, (FloatField, DoubleField)):
            data[field.name] = 0.0
        else:
            data[field.name] = ''
    data.update({
        'match_id': match_id, 'player_id': player_id, 'nickname': 'Player',
        'team': 1, 'cup_name': 'demo-cup', 'play_day': '20260830',
        'game_count': 10,
    })
    data.update(values)
    return MatchPlayer.create(**data)


def parsed_payload(steam_id, kills=15):
    return {
        'map_data': {'map_name': 'de_mirage', 'total_rounds': 10},
        'players': {
            str(steam_id): {
                'steam_id': int(steam_id), 'name': 'Player', 'team_id': 1, 'deaths': 5,
                'deaths_traded': {'total': 2, 'ct': 1, 't': 1},
                'kill_stats': {'total': kills, 'headshots': 7, 'trade_kills': 3,
                               'team_kills': 0, 'weapons_kills': {'AK-47': 10}},
                'assist_stats': {'total': 4, 'flashed_enemies': 2,
                                 'damage_given': 1000, 'adr': 100},
                'player_map_stats': {
                    'mvps': 2, 'aces': 1, 'multi_kills': {'k2': 2, 'k3': 1, 'k4': 0, 'k5': 1},
                    'clutches_won': 1, 'kast': 80,
                    'approx_ekast_percent': 82, 'approx_round_swing_percent': 4,
                },
                'opening_duel_stats': {
                    'opening_kills': {'total': 3, 'ct': 2, 't': 1},
                    'opening_deaths': {'total': 1, 'ct': 0, 't': 1},
                    'opening_success_rate': 66.6667,
                },
                'side_stats': {
                    'rounds': {'total': 10, 'ct': 5, 't': 5},
                    'kills': {'total': kills, 'ct': 8, 't': kills - 8},
                    'deaths': {'total': 5, 'ct': 2, 't': 3},
                    'adr': {'ct': 110, 't': 90}, 'kast': {'ct': 80, 't': 80},
                },
                'utility_stats': {
                    'enemies_flashed': 6, 'friends_flashed': 2,
                    'enemy_flash_time_seconds': 12,
                    'average_enemy_flash_time_seconds': 2,
                    'utility_damage': {'total': 120, 'he': 70, 'fire': 50},
                    'grenades_thrown': {'total': 12, 'flash': 4, 'smoke': 3, 'he': 2,
                                        'molotov': 1, 'incendiary': 1, 'decoy': 1},
                    'unused_utility_value': 600,
                },
                'rating': {'value': 1.22, 'kills': 1.2, 'damage': 1.1, 'survival': 1.0,
                           'kast': 1.05, 'multi_kill': 1.3, 'round_swing': 1.1},
            },
            '76561198000000002': {
                'steam_id': 76561198000000002, 'name': 'Other', 'deaths': 10,
                'kill_stats': {}, 'assist_stats': {}, 'player_map_stats': {},
                'opening_duel_stats': {}, 'side_stats': {}, 'utility_stats': {}, 'rating': {},
            },
        },
    }


class DemoAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp(prefix='cs-demo-tests-')
        if not db.is_closed():
            db.close()
        db.init(os.path.join(cls.temp_dir, 'test.db'))
        create_tables()

    @classmethod
    def tearDownClass(cls):
        if not db.is_closed():
            db.close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def setUp(self):
        DemoPlayerStats.delete().execute()
        DemoAnalysis.delete().execute()
        DemoCredential.delete().execute()
        MatchPlayer.delete().execute()
        Player.delete().execute()
        Config.delete().where(Config.key == 'demo_analysis_enabled').execute()

    def test_demo_job_id_is_accepted_by_rq(self):
        first = _demo_job_id(7, 'PVP@123:456', 'v1.0/beta')
        second = _demo_job_id(7, 'PVP@123:456', 'v1.0/beta')

        validate_job_id(first)
        self.assertEqual(first, second)
        self.assertRegex(first, r'^demo-analysis-7-[a-f0-9]{16}$')

    def test_credentials_are_encrypted_and_round_trip(self):
        key = Fernet.generate_key().decode()
        token = 'a-secret-access-token-value'
        with patch('demo_service.DEMO_CREDENTIAL_ENCRYPTION_KEY', key):
            save_demo_credential('76561198000000001', token)
            row = DemoCredential.get()
            self.assertNotIn(token, row.encrypted_access_token)
            self.assertEqual(load_demo_credential()['access_token'], token)
            self.assertEqual(load_demo_credential()['source'], 'database')

    def test_existing_wmpvp_credential_is_the_default_fallback(self):
        with patch('demo_service.WMPVP_ACCESS_TOKEN', 'existing-wmpvp-token'), \
                patch('demo_service.WMPVP_STEAM_ID', '76561198000000001'):
            credential = load_demo_credential()
        self.assertEqual(credential, {
            'steam_id': '76561198000000001',
            'access_token': 'existing-wmpvp-token',
            'source': 'wmpvp_default',
        })

    def test_database_credential_takes_precedence_over_env_fallback(self):
        key = Fernet.generate_key().decode()
        with patch('demo_service.DEMO_CREDENTIAL_ENCRYPTION_KEY', key), \
                patch('demo_service.WMPVP_ACCESS_TOKEN', 'env-token'), \
                patch('demo_service.WMPVP_STEAM_ID', '76561198000000001'):
            save_demo_credential('76561198000000002', 'database-access-token')
            credential = load_demo_credential()
        self.assertEqual(credential['steam_id'], '76561198000000002')
        self.assertEqual(credential['access_token'], 'database-access-token')
        self.assertEqual(credential['source'], 'database')

    def test_demo_enabled_switch_is_stored_in_database(self):
        self.assertFalse(demo_analysis_enabled())
        set_demo_analysis_enabled(True)
        self.assertTrue(demo_analysis_enabled())
        self.assertEqual(Config.get_value('demo_analysis_enabled'), '1')
        set_demo_analysis_enabled(False)
        self.assertFalse(demo_analysis_enabled())

    def test_admin_api_never_echoes_demo_access_token(self):
        key = Fernet.generate_key().decode()
        token = 'another-secret-access-token'
        client = app.test_client()
        with client.session_transaction() as session:
            session['admin_user'] = 'admin'
        with patch('demo_service.DEMO_CREDENTIAL_ENCRYPTION_KEY', key):
            response = client.post('/api/admin/demo-settings', json={
                'action': 'save', 'steam_id': '76561198000000001',
                'access_token': token,
            })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(token, response.get_data(as_text=True))
        self.assertNotIn(token, DemoCredential.get().encrypted_access_token)

    def test_missing_encryption_key_refuses_plaintext_storage(self):
        with patch('demo_service.DEMO_CREDENTIAL_ENCRYPTION_KEY', ''):
            with self.assertRaisesRegex(ValueError, 'DEMO_CREDENTIAL_ENCRYPTION_KEY'):
                save_demo_credential('76561198000000001', 'a-secret-access-token-value')
        self.assertEqual(DemoCredential.select().count(), 0)

    def test_missing_credentials_produce_explicit_blocked_state(self):
        set_demo_analysis_enabled(True)
        with patch('demo_service.WMPVP_ACCESS_TOKEN', ''), \
                patch('demo_service.WMPVP_STEAM_ID', ''):
            row = schedule_demo_analysis('PVP@123')
        self.assertEqual(row.status, 'blocked_credentials')
        self.assertEqual(row.error_code, 'credentials_missing')

    def test_manual_retry_replaces_scheduled_rq_retry(self):
        set_demo_analysis_enabled(True)
        existing = MagicMock()
        existing.get_status.return_value = 'scheduled'
        queue = MagicMock()
        queue.fetch_job.return_value = existing

        with patch('demo_tasks.has_demo_credential', return_value=True), \
                patch('demo_tasks._queue', return_value=queue):
            row = schedule_demo_analysis('PVP@manual-retry', force=True)

        existing.cancel.assert_called_once_with()
        existing.delete.assert_called_once_with()
        queue.enqueue.assert_called_once()
        self.assertEqual(row.status, 'queued')
        self.assertIsNone(row.error_message)

    def test_automatic_scheduling_keeps_existing_scheduled_retry(self):
        set_demo_analysis_enabled(True)
        existing = MagicMock()
        existing.get_status.return_value = 'scheduled'
        queue = MagicMock()
        queue.fetch_job.return_value = existing

        with patch('demo_tasks.has_demo_credential', return_value=True), \
                patch('demo_tasks._queue', return_value=queue):
            row = schedule_demo_analysis('PVP@automatic-retry')

        existing.cancel.assert_not_called()
        existing.delete.assert_not_called()
        queue.enqueue.assert_not_called()
        self.assertEqual(row.status, 'pending')

    def test_sensitive_query_values_are_redacted_from_errors(self):
        token = 'secret-token-value'
        oss_key = 'LTAI-secret-key'
        signature = 'signed-secret-value'
        message = _safe_error(
            RuntimeError(
                f'https://example.test/demo?access_token={token}&match_id=1'
                f'&OSSAccessKeyId={oss_key}&Signature={signature}'
            ),
            (token,),
        )
        self.assertNotIn(token, message)
        self.assertNotIn(oss_key, message)
        self.assertNotIn(signature, message)
        self.assertIn('[REDACTED]', message)

    def test_demo_worker_runs_scheduler_for_interval_retries(self):
        connection = MagicMock()
        worker = MagicMock()
        with patch.object(demo_worker, 'REDIS_URL', 'redis://example.test/0'), \
                patch.object(demo_worker.Redis, 'from_url', return_value=connection), \
                patch.object(demo_worker, 'Queue') as queue_class, \
                patch.object(demo_worker, 'Worker', return_value=worker):
            demo_worker.main()

        queue_class.assert_called_once()
        worker.work.assert_called_once_with(with_scheduler=True)

    def test_bzip_demo_is_bounded_extracted_and_header_checked(self):
        root = Path(self.temp_dir)
        source = root / 'sample.bz2'
        target = root / 'sample.dem'
        source.write_bytes(bz2.compress(b'PBDEMS2\x00payload'))
        _extract_demo(source, target)
        self.assertTrue(target.read_bytes().startswith(b'PBDEMS2'))
        source.write_bytes(b'not-a-demo')
        with self.assertRaisesRegex(ValueError, 'PBDEMS2'):
            _extract_demo(source, target)

    def test_completed_demo_archives_are_deleted_after_three_days(self):
        now = datetime(2026, 9, 5, 12, 0, 0)
        storage = Path(self.temp_dir) / 'retention-storage'
        old_dir = storage / 'aa' / ('a' * 64)
        recent_dir = storage / 'bb' / ('b' * 64)
        old_dir.mkdir(parents=True)
        recent_dir.mkdir(parents=True)
        old_demo = old_dir / 'match.dem.zst'
        old_result = old_dir / 'analysis-v1.json.zst'
        recent_demo = recent_dir / 'match.dem.zst'
        old_demo.write_bytes(b'old-demo')
        old_result.write_bytes(b'old-result')
        recent_demo.write_bytes(b'recent-demo')
        old = DemoAnalysis.create(
            match_id='retention-old', status='completed',
            finished_at=now - timedelta(days=3, seconds=1),
            archive_path=str(old_demo), raw_result_path=str(old_result),
        )
        recent = DemoAnalysis.create(
            match_id='retention-recent', status='completed',
            finished_at=now - timedelta(days=2), archive_path=str(recent_demo),
        )

        with patch('demo_tasks.DEMO_STORAGE_PATH', str(storage)):
            stats = cleanup_demo_archives(retention_days=3, now=now)

        old = DemoAnalysis.get_by_id(old.id)
        recent = DemoAnalysis.get_by_id(recent.id)
        self.assertFalse(old_demo.exists())
        self.assertFalse(old_result.exists())
        self.assertIsNone(old.archive_path)
        self.assertIsNone(old.raw_result_path)
        self.assertEqual(old.status, 'completed')
        self.assertTrue(recent_demo.exists())
        self.assertEqual(recent.archive_path, str(recent_demo))
        self.assertEqual(stats['files_deleted'], 2)
        self.assertEqual(stats['rows_cleaned'], 1)

    def test_demo_cleanup_never_deletes_outside_storage_or_active_shared_file(self):
        now = datetime(2026, 9, 5, 12, 0, 0)
        storage = Path(self.temp_dir) / 'safe-retention-storage'
        storage.mkdir()
        shared = storage / 'shared.dem.zst'
        outside = Path(self.temp_dir) / 'outside.dem.zst'
        shared.write_bytes(b'shared')
        outside.write_bytes(b'outside')
        old_shared = DemoAnalysis.create(
            match_id='retention-old-shared', status='completed',
            finished_at=now - timedelta(days=4), archive_path=str(shared),
        )
        recent_shared = DemoAnalysis.create(
            match_id='retention-active-shared', status='parsing',
            finished_at=None, archive_path=str(shared),
        )
        unsafe = DemoAnalysis.create(
            match_id='retention-unsafe', status='completed',
            finished_at=now - timedelta(days=4), archive_path=str(outside),
        )

        with patch('demo_tasks.DEMO_STORAGE_PATH', str(storage)):
            stats = cleanup_demo_archives(retention_days=3, now=now)

        old_shared = DemoAnalysis.get_by_id(old_shared.id)
        recent_shared = DemoAnalysis.get_by_id(recent_shared.id)
        unsafe = DemoAnalysis.get_by_id(unsafe.id)
        self.assertTrue(shared.exists())
        self.assertIsNone(old_shared.archive_path)
        self.assertEqual(recent_shared.archive_path, str(shared))
        self.assertTrue(outside.exists())
        self.assertEqual(unsafe.archive_path, str(outside))
        self.assertEqual(stats['shared'], 1)
        self.assertEqual(stats['failed'], 1)

    def test_demo_is_canonical_per_completed_match_and_fallback_stays(self):
        steam_id = '76561198000000001'
        Player.create(player_id='platform-player', nickname='Player', steam_id=steam_id)
        create_platform_row('m-demo', 'platform-player', kill=5, death=9, dmg_health=400, kast=5)
        create_platform_row('m-fallback', 'platform-player', kill=20, death=10,
                            dmg_health=800, kast=7)
        DemoAnalysis.create(match_id='m-demo', status='completed', metric_version='v1')

        count = persist_analysis('m-demo', parsed_payload(steam_id))
        self.assertEqual(count, 2)
        platform = {'match_count': 2, 'total_kills': 25, 'total_deaths': 19,
                    'avg_pw_rating': 1.1}
        result = attach_demo_stats(platform, 'demo-cup', 'platform-player')

        self.assertEqual(result['total_kills'], 35)  # 15 Demo + 20 fallback
        self.assertEqual(result['total_deaths'], 15)  # 5 Demo + 10 fallback
        self.assertEqual(result['demo_data']['enemies_flashed'], 6)
        self.assertEqual(result['demo_data']['avg_flash_thrown_per_match'], 4)
        self.assertEqual(result['demo_data']['avg_enemies_flashed_per_match'], 6)
        self.assertEqual(result['demo_data']['avg_grenades_thrown_per_match'], 12)
        self.assertEqual(result['demo_data']['avg_unused_utility_value_per_match'], 600)
        self.assertEqual(result['demo_data']['avg_trade_frags_per_match'], 3)
        self.assertEqual(result['demo_data']['ct_kills_per_round'], 1.6)
        self.assertEqual(result['demo_data']['t_kills_per_round'], 1.4)
        self.assertEqual(result['demo_data']['approx_round_swing_percent'], 4)
        self.assertEqual(result['demo_coverage'], {'completed': 1, 'total': 2, 'ratio': 0.5})
        self.assertEqual(result['metric_source'], 'mixed')
        self.assertEqual(result['platform_data']['total_kills'], 25)

    def test_demo_event_counts_expose_per_match_averages(self):
        steam_id = '76561198000000001'
        Player.create(player_id='average-player', nickname='Player', steam_id=steam_id)
        for match_id in ('m-average-1', 'm-average-2'):
            create_platform_row(match_id, 'average-player')
            DemoAnalysis.create(match_id=match_id, status='completed', metric_version='v1')
            persist_analysis(match_id, parsed_payload(steam_id))

        result = attach_demo_stats({'match_count': 2}, 'demo-cup', 'average-player')
        demo = result['demo_data']

        self.assertEqual(demo['flash_thrown'], 8)
        self.assertEqual(demo['avg_flash_thrown_per_match'], 4)
        self.assertEqual(demo['enemies_flashed'], 12)
        self.assertEqual(demo['avg_enemies_flashed_per_match'], 6)
        self.assertEqual(demo['unused_utility_value'], 1200)
        self.assertEqual(demo['avg_unused_utility_value_per_match'], 600)
        self.assertEqual(result['demo_coverage'], {'completed': 2, 'total': 2, 'ratio': 1.0})

    def test_round_swing_percent_is_weighted_by_demo_rounds(self):
        steam_id = '76561198000000001'
        Player.create(player_id='swing-player', nickname='Player', steam_id=steam_id)
        fixtures = (
            ('m-swing-short', 10, 4),
            ('m-swing-long', 30, -2),
        )
        for match_id, rounds, swing in fixtures:
            create_platform_row(match_id, 'swing-player', game_count=rounds)
            DemoAnalysis.create(match_id=match_id, status='completed', metric_version='v1')
            payload = parsed_payload(steam_id)
            payload['map_data']['total_rounds'] = rounds
            player = payload['players'][steam_id]
            player['side_stats']['rounds'] = {
                'total': rounds, 'ct': rounds // 2, 't': rounds - rounds // 2,
            }
            player['player_map_stats']['approx_round_swing_percent'] = swing
            persist_analysis(match_id, payload)

        result = attach_demo_stats({'match_count': 2}, 'demo-cup', 'swing-player')

        self.assertEqual(result['demo_data']['total_rounds'], 40)
        self.assertEqual(result['demo_data']['approx_round_swing_percent'], -0.5)
        self.assertEqual(result['approx_round_swing_percent'], -0.5)

    def test_roster_mismatch_is_rejected_without_partial_rows(self):
        Player.create(player_id='platform-player', nickname='Player', steam_id='76561198000000009')
        create_platform_row('m-bad', 'platform-player')
        with self.assertRaisesRegex(ValueError, '80%'):
            persist_analysis('m-bad', parsed_payload('76561198000000001'))
        self.assertEqual(DemoPlayerStats.select().where(
            DemoPlayerStats.match_id == 'm-bad').count(), 0)


if __name__ == '__main__':
    unittest.main()
