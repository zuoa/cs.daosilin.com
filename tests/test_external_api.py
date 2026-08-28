import os
import shutil
import tempfile
import unittest
from datetime import datetime


TEST_DIR = tempfile.mkdtemp(prefix='cs-external-api-')
os.environ['DB_PATH'] = os.path.join(TEST_DIR, 'test.db')
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
os.environ['EXTERNAL_API_TOKEN'] = 'test-token'
os.environ['ADMIN_PASSWORD'] = 'test-admin-password'

from app import app  # noqa: E402
from auth import EXTERNAL_TOKEN_HASH_KEY, EXTERNAL_TOKEN_HINT_KEY  # noqa: E402
from database import Config, Match, MatchPlayer, MatchSelection, Player, Season, db  # noqa: E402
from peewee import BooleanField, FloatField, IntegerField  # noqa: E402


def create_match_player(match_id, player_id, cup_name, **values):
    data = {}
    for field in MatchPlayer._meta.sorted_fields:
        if field.primary_key or field.default is not None or field.null:
            continue
        if isinstance(field, BooleanField):
            data[field.name] = False
        elif isinstance(field, IntegerField):
            data[field.name] = 0
        elif isinstance(field, FloatField):
            data[field.name] = 0.0
        else:
            data[field.name] = ''
    data.update({
        'match_id': match_id,
        'player_id': player_id,
        'nickname': player_id,
        'team': 1,
        'cup_name': cup_name,
        'play_day': '20250101',
        'game_count': 1,
    })
    data.update(values)
    return MatchPlayer.create(**data)


class ExternalPlayersApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config.update(TESTING=True, EXTERNAL_API_TOKEN='test-token')
        Player.create(
            player_id='p1', nickname='选手一', alias_name='One', steam_id='steam-p1',
            live_url='https://example.com/p1', in_library=True,
        )
        Player.create(player_id='p2', nickname='选手二', in_library=True)
        Season.create(
            cup_name='season-one', cup_alias='赛季一', name='赛季一',
            start_date=datetime(2024, 1, 1), end_date=datetime(2024, 6, 1),
            status='archived', match_type='custom',
        )
        Season.create(
            cup_name='season-two', cup_alias='赛季二', name='赛季二',
            start_date=datetime(2025, 1, 1), end_date=datetime(2025, 6, 1),
            status='archived', match_type='custom',
        )
        Season.create(
            cup_name='current-season', cup_alias='当前赛季', name='当前赛季',
            start_date=datetime(2098, 1, 1), end_date=datetime(2099, 6, 1),
            status='active', match_type='custom',
        )
        create_match_player(
            'm1', 'p1', 'season-one', kill=10, death=5, entry_kill=2,
            first_death=2, rating=1.0, adpr=80.0, win=1,
        )
        create_match_player(
            'm2', 'p1', 'season-two', kill=20, death=10, entry_kill=3,
            first_death=1, rating=2.0, adpr=100.0, win=0,
        )
        Match.create(
            match_id='m2', map_name='炼狱小镇', map_name_en='de_inferno',
            start_time=datetime(2025, 2, 3, 20, 15, 30),
            end_time=datetime(2025, 2, 3, 20, 55, 30), duration=2400,
            win_team=2, team1_name='Alpha', team1_score=9, team1_half_score=5,
            team2_name='Bravo', team2_score=13, team2_half_score=7,
            game_mode='MR12', cup_name='season-two', play_day='20250101',
        )
        MatchSelection.create(
            match_id='m2', season_cup_name='season-two', status='approved',
            source_type='custom', play_day='20250101', roster_hit_count=1,
        )
        create_match_player(
            'm3', 'p2', 'current-season', kill=30, death=10, entry_kill=4,
            first_death=2, rating=3.0, adpr=120.0, win=1,
        )

    @classmethod
    def tearDownClass(cls):
        if not db.is_closed():
            db.close()
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def setUp(self):
        self.client = app.test_client()
        self.auth = {'Authorization': 'Bearer test-token'}

    def test_token_is_required(self):
        response = self.client.get('/api/v1/external/players?season=all')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get('WWW-Authenticate'), 'Bearer')

        response = self.client.get(
            '/api/v1/external/players?season=all',
            headers={'Authorization': 'Bearer wrong'},
        )
        self.assertEqual(response.status_code, 401)

    def test_last_returns_latest_completed_season(self):
        response = self.client.get('/api/v1/external/players?season=last', headers=self.auth)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['seasons'][0]['cup_name'], 'season-two')
        self.assertEqual(payload['player_count'], 1)
        player = payload['players'][0]
        self.assertEqual(player['avg_adpr'], 100.0)
        self.assertEqual(player['avg_rating'], 2.0)
        self.assertEqual(player['fk_fd_ratio'], 3.0)

    def test_all_combines_all_configured_seasons(self):
        response = self.client.get(
            '/api/v1/external/players/all',
            headers={'X-API-Token': 'test-token'},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['player_count'], 2)
        p1 = next(player for player in payload['players'] if player['player_id'] == 'p1')
        self.assertEqual(p1['match_count'], 2)
        self.assertEqual(p1['total_kills'], 30)
        self.assertEqual(p1['avg_rating'], 1.5)
        self.assertEqual(p1['avg_adpr'], 90.0)
        self.assertEqual(p1['fk_fd_ratio'], 1.6667)

    def test_admin_can_generate_and_revoke_database_token(self):
        app.config['EXTERNAL_API_TOKEN'] = ''
        Config.delete().where(Config.key.in_([
            EXTERNAL_TOKEN_HASH_KEY, EXTERNAL_TOKEN_HINT_KEY,
        ])).execute()
        try:
            with self.client.session_transaction() as session:
                session['admin_user'] = 'admin'

            response = self.client.post(
                '/api/admin/external-api-token', json={'action': 'generate'},
            )
            self.assertEqual(response.status_code, 200)
            generated = response.get_json()['data']['token']
            self.assertGreaterEqual(len(generated), 32)
            self.assertNotEqual(Config.get_value(EXTERNAL_TOKEN_HASH_KEY), generated)
            self.assertEqual(Config.get_value(EXTERNAL_TOKEN_HINT_KEY), generated[-4:])

            status_response = self.client.get('/api/admin/external-api-token')
            status = status_response.get_json()['data']
            self.assertEqual(status['source'], 'database')
            self.assertNotIn('token', status)

            api_response = self.client.get(
                '/api/v1/external/players?season=last',
                headers={'Authorization': f'Bearer {generated}'},
            )
            self.assertEqual(api_response.status_code, 200)

            revoke_response = self.client.post(
                '/api/admin/external-api-token', json={'action': 'revoke'},
            )
            self.assertEqual(revoke_response.status_code, 200)
            self.assertEqual(
                self.client.get(
                    '/api/v1/external/players?season=last',
                    headers={'Authorization': f'Bearer {generated}'},
                ).status_code,
                503,
            )
        finally:
            Config.delete().where(Config.key.in_([
                EXTERNAL_TOKEN_HASH_KEY, EXTERNAL_TOKEN_HINT_KEY,
            ])).execute()
            app.config['EXTERNAL_API_TOKEN'] = 'test-token'

    def test_season_can_be_selected_by_display_name(self):
        response = self.client.get('/api/v1/external/players/赛季一', headers=self.auth)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['seasons'][0]['cup_name'], 'season-one')
        self.assertEqual(payload['players'][0]['avg_rating'], 1.0)

    def test_unknown_season_returns_404(self):
        response = self.client.get(
            '/api/v1/external/players?season=missing', headers=self.auth,
        )
        self.assertEqual(response.status_code, 404)

    def test_player_detail_includes_season_match_records(self):
        response = self.client.get('/api/v1/player/p1?cup=season-two')
        self.assertEqual(response.status_code, 200)
        records = response.get_json()['data']['match_records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['match_id'], 'm2')
        self.assertEqual(records[0]['start_time'], '2025-02-03T20:15:30')
        self.assertEqual(records[0]['kill'], 20)
        self.assertEqual(records[0]['team1_name'], 'Alpha')

    def test_admin_match_list_exposes_exact_start_time(self):
        with self.client.session_transaction() as session:
            session['admin_user'] = 'admin'
        response = self.client.get(
            '/api/admin/selection/list?cup=season-two&status=approved',
        )
        self.assertEqual(response.status_code, 200)
        records = response.get_json()['data']['list']
        self.assertEqual(records[0]['start_time'], '2025-02-03T20:15:30')


if __name__ == '__main__':
    unittest.main()
