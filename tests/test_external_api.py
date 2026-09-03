import os
import io
import shutil
import tempfile
import unittest
import json
from datetime import date, datetime
from unittest.mock import patch


TEST_DIR = tempfile.mkdtemp(prefix='cs-external-api-')
os.environ['DB_PATH'] = os.path.join(TEST_DIR, 'test.db')
os.environ['DATABASE_URL'] = ''
os.environ['REDIS_URL'] = ''
os.environ['EXTERNAL_API_TOKEN'] = 'test-token'
os.environ['ADMIN_PASSWORD'] = 'test-admin-password'

from app import app  # noqa: E402
from cache_service import cache, invalidate_season  # noqa: E402
from auth import EXTERNAL_TOKEN_HASH_KEY, EXTERNAL_TOKEN_HINT_KEY  # noqa: E402
from database import (Config, CupDayChampion, Match, MatchPlayer, MatchSelection,
                      Player, PlayerCommunityRating, PlayerSeasonSummary, PlayerTitle, Season,
                      SeasonRoster, db)  # noqa: E402
from peewee import BooleanField, FloatField, IntegerField  # noqa: E402
from scheduler import set_crawl_status  # noqa: E402


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
            live_url='https://www.douyu.com/731778', in_library=True,
            perfect_score=1513, perfect_level='B',
            perfect_rank_updated_at=datetime(2025, 2, 4, 8, 30),
        )
        Player.create(
            player_id='p2', nickname='选手二',
            live_url='https://www.huya.com/731778', in_library=True,
        )
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
            first_death=2, rating=9.0, pw_rating=1.0, adpr=80.0, dmg_health=800,
            game_count=10, kast=7, headshot=4, flash_success=5,
            flash_teammate=1, throws_count=10, trade_frag_count=2,
            grenade_damage=50, inferno_damage=30, win=1,
        )
        create_match_player(
            'm2', 'p1', 'season-two', kill=20, death=10, entry_kill=3,
            first_death=1, rating=9.0, pw_rating=2.0, adpr=100.0, dmg_health=2000,
            game_count=20, kast=15, headshot=10, flash_success=8,
            flash_teammate=2, throws_count=16, trade_frag_count=6,
            grenade_damage=40, inferno_damage=60, kill_map=json.dumps({'p2': 3}),
            win=0,
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
            first_death=2, rating=9.0, pw_rating=3.0, adpr=120.0, dmg_health=2880,
            game_count=24, kast=18, win=1,
        )
        PlayerSeasonSummary.create(
            player_id='p1', cup_name='season-one', status='pending',
        )
        PlayerSeasonSummary.create(
            player_id='p1', cup_name='season-two', status='completed',
            headline='稳定火力点', overview='赛季表现稳定，关键数据有足够样本支持。',
            strength='持续输出能力突出。', weakness='部分地图样本仍需积累。',
            style='重视效率的稳健打法。', sample_info='{"比赛场次": 1}',
            source_hash='same', requested_hash='same',
            generated_at=datetime(2025, 2, 4, 9, 0),
        )

    @classmethod
    def tearDownClass(cls):
        if not db.is_closed():
            db.close()
        shutil.rmtree(TEST_DIR, ignore_errors=True)

    def setUp(self):
        self.client = app.test_client()
        self.auth = {'Authorization': 'Bearer test-token'}
        PlayerCommunityRating.delete().execute()

    def test_community_rating_is_hidden_until_today_vote(self):
        response = self.client.get(
            '/api/v1/player/p1/community-rating?cup=season-one',
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertFalse(payload['voted_today'])
        self.assertFalse(payload['results_visible'])
        self.assertIsNone(payload['total_votes'])
        self.assertNotIn('count', payload['options'][0])

    def test_community_rating_same_day_updates_instead_of_adding(self):
        first = self.client.post(
            '/api/v1/player/p1/community-rating?cup=season-one',
            json={'score': 5},
        )
        self.assertEqual(first.status_code, 200)
        self.assertIn('cs_community_voter=', first.headers.get('Set-Cookie', ''))
        self.assertEqual(first.get_json()['data']['total_votes'], 1)

        changed = self.client.post(
            '/api/v1/player/p1/community-rating?cup=season-one',
            json={'score': 2},
        )
        payload = changed.get_json()['data']
        self.assertEqual(payload['viewer_score'], 2)
        self.assertEqual(payload['total_votes'], 1)
        self.assertEqual(PlayerCommunityRating.select().count(), 1)

    def test_community_rating_allows_one_new_vote_next_day(self):
        with patch('community_rating_service.rating_today', return_value=date(2026, 9, 2)):
            self.client.post(
                '/api/v1/player/p1/community-rating?cup=season-one',
                json={'score': 4},
            )
        with patch('community_rating_service.rating_today', return_value=date(2026, 9, 3)):
            response = self.client.post(
                '/api/v1/player/p1/community-rating?cup=season-one',
                json={'score': 5},
            )
        payload = response.get_json()['data']
        self.assertEqual(payload['viewer_score'], 5)
        self.assertEqual(payload['total_votes'], 2)
        self.assertEqual(PlayerCommunityRating.select().count(), 2)

    def test_community_rating_consensus_uses_weighted_average(self):
        payload = None
        for score in (4, 4, 4, 5, 5):
            response = app.test_client().post(
                '/api/v1/player/p1/community-rating?cup=season-one',
                json={'score': score},
            )
            payload = response.get_json()['data']
        self.assertEqual(payload['total_votes'], 5)
        self.assertEqual(payload['consensus']['status'], 'formed')
        self.assertEqual(payload['consensus']['score'], 4.4)
        self.assertEqual(payload['consensus']['raw_average'], 4.4)
        self.assertEqual(payload['consensus']['label'], '顶级')
        self.assertEqual(payload['consensus']['label_method'], 'raw_average')
        self.assertEqual(payload['consensus']['method'], 'bayesian_average')

        updated = app.test_client().post(
            '/api/v1/player/p1/community-rating?cup=season-one',
            json={'score': 5},
        ).get_json()['data']
        self.assertEqual(updated['total_votes'], 6)
        self.assertEqual(updated['consensus']['status'], 'formed')
        self.assertEqual(updated['consensus']['score'], 4.5)
        self.assertEqual(updated['consensus']['label'], '夯')

    def test_cup_leaderboard_uses_season_prior_and_minimum_sample(self):
        today = date(2026, 9, 2)
        for index in range(5):
            PlayerCommunityRating.create(
                player_id='p1', cup_name='season-one', voter_hash=f'high-{index}',
                vote_date=today, score=5,
            )
            PlayerCommunityRating.create(
                player_id='p2', cup_name='season-one', voter_hash=f'low-{index}',
                vote_date=today, score=1,
            )
        cache.clear()

        payload = self.client.get('/api/v1/cup/season-one').get_json()['data']
        rating = payload['players'][0]['community_rating']
        self.assertEqual(rating['status'], 'formed')
        self.assertEqual(rating['raw_average'], 5.0)
        self.assertEqual(rating['score'], 4.0)
        self.assertEqual(rating['label'], '夯')
        self.assertEqual(rating['label_method'], 'raw_average')
        self.assertEqual(rating['total_votes'], 5)
        self.assertEqual(rating['minimum_votes'], 5)

    def test_community_label_follows_real_votes_not_weighted_prior(self):
        today = date(2026, 9, 2)
        for index in range(5):
            PlayerCommunityRating.create(
                player_id='p1', cup_name='season-one', voter_hash=f'low-{index}',
                vote_date=today, score=1,
            )
        PlayerCommunityRating.create(
            player_id='p1', cup_name='season-one', voter_hash='npc',
            vote_date=today, score=2,
        )
        for index in range(10):
            PlayerCommunityRating.create(
                player_id='p2', cup_name='season-one', voter_hash=f'high-{index}',
                vote_date=today, score=5,
            )
        cache.clear()

        payload = self.client.get('/api/v1/cup/season-one').get_json()['data']
        rating = next(
            player['community_rating'] for player in payload['players']
            if player['player_id'] == 'p1'
        )
        self.assertEqual(rating['raw_average'], 1.17)
        self.assertEqual(rating['score'], 2.26)
        self.assertEqual(rating['label'], '拉完了')
        self.assertEqual(rating['label_method'], 'raw_average')

    def test_community_rating_vote_invalidates_cup_leaderboard_cache(self):
        cache.clear()
        path = '/api/v1/cup/season-one'
        self.assertEqual(self.client.get(path).headers.get('X-Cache'), 'MISS')
        self.assertEqual(self.client.get(path).headers.get('X-Cache'), 'HIT')

        response = self.client.post(
            '/api/v1/player/p1/community-rating?cup=season-one',
            json={'score': 4},
        )
        self.assertEqual(response.status_code, 200)

        refreshed = self.client.get(path)
        self.assertEqual(refreshed.headers.get('X-Cache'), 'MISS')
        rating = refreshed.get_json()['data']['players'][0]['community_rating']
        self.assertEqual(rating['status'], 'collecting')
        self.assertEqual(rating['total_votes'], 1)

    def test_community_rating_validates_score_and_target(self):
        invalid_score = self.client.post(
            '/api/v1/player/p1/community-rating?cup=season-one',
            json={'score': 6},
        )
        self.assertEqual(invalid_score.status_code, 400)
        missing_target = self.client.get(
            '/api/v1/player/missing/community-rating?cup=season-one',
        )
        self.assertEqual(missing_target.status_code, 404)

    def test_token_is_required(self):
        response = self.client.get('/api/v1/external/players?season=all')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers.get('WWW-Authenticate'), 'Bearer')

        response = self.client.get(
            '/api/v1/external/players?season=all',
            headers={'Authorization': 'Bearer wrong'},
        )
        self.assertEqual(response.status_code, 401)

    def test_cup_days_are_returned_in_descending_order(self):
        cup_name = 'day-order-season'
        try:
            for day in ('20260827', '20260829', '20260828'):
                for index in range(2):
                    create_match_player(
                        f'order-{day}-{index}',
                        f'order-player-{day}-{index}',
                        cup_name,
                        play_day=day,
                    )

            self.assertEqual(
                MatchPlayer.get_cup_day_set(cup_name),
                ['20260829', '20260828', '20260827'],
            )
        finally:
            (MatchPlayer
             .delete()
             .where(MatchPlayer.cup_name == cup_name)
             .execute())

    def test_last_returns_latest_completed_season(self):
        response = self.client.get('/api/v1/external/players?season=last', headers=self.auth)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['seasons'][0]['cup_name'], 'season-two')
        self.assertEqual(payload['player_count'], 1)
        player = payload['players'][0]
        self.assertEqual(set(player), {
            'player_id', 'nickname', 'avatar', 'alias_name', 'steam_id',
            'live_url', 'live_room_id', 'match_count', 'win_count', 'win_rate',
            'total_rounds', 'total_kills', 'total_deaths', 'total_assists',
            'kd_ratio', 'total_first_kills', 'total_first_deaths',
            'fk_fd_ratio', 'total_headshots', 'avg_headshot_ratio',
            'total_mvp', 'avg_rating',
            'avg_pw_rating', 'avg_adpr', 'avg_kast', 'perfect_rank',
            'scouting_reports',
        })
        self.assertEqual(player['avg_adpr'], 100.0)
        self.assertEqual(player['avg_kast'], 0.75)
        self.assertEqual(player['avg_headshot_ratio'], 0.5)
        self.assertEqual(player['avg_rating'], 2.0)
        self.assertEqual(player['avg_pw_rating'], 2.0)
        self.assertEqual(player['fk_fd_ratio'], 3.0)
        self.assertEqual(player['perfect_rank'], {
            'score': 1513,
            'level': 'B',
            'stars': None,
            'updated_at': '2025-02-04T08:30:00',
        })
        self.assertEqual(len(player['scouting_reports']), 1)
        report = player['scouting_reports'][0]
        self.assertEqual(report['cup_name'], 'season-two')
        self.assertEqual(report['season_name'], '赛季二')
        self.assertEqual(report['report']['headline'], '稳定火力点')
        self.assertEqual(report['report']['status'], 'completed')

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
        self.assertEqual(p1['avg_pw_rating'], 1.5)
        self.assertEqual(p1['avg_adpr'], 93.3333)
        self.assertEqual(p1['avg_kast'], 0.7333)
        self.assertEqual(p1['avg_headshot_ratio'], 0.4667)
        self.assertEqual(p1['fk_fd_ratio'], 1.6667)
        self.assertEqual(p1['live_room_id'], 'DOUYU_731778')
        for demo_field in (
            'platform_data', 'demo_data', 'demo_coverage', 'demo_analysis',
            'metric_source',
        ):
            self.assertNotIn(demo_field, p1)
        p2 = next(player for player in payload['players'] if player['player_id'] == 'p2')
        self.assertEqual(p2['perfect_rank'], {
            'score': None,
            'level': None,
            'stars': None,
            'updated_at': None,
        })
        self.assertEqual(p2['scouting_reports'], [])

    def test_external_player_can_be_queried_by_steam_id(self):
        response = self.client.get(
            '/api/v1/external/player?steam_id=steam-p1&season=all',
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['lookup'], {'type': 'steam_id', 'value': 'steam-p1'})
        self.assertEqual(payload['player']['player_id'], 'p1')
        self.assertEqual(payload['player']['match_count'], 2)
        self.assertEqual(
            [item['cup_name'] for item in payload['player']['scouting_reports']],
            ['season-two', 'season-one'],
        )
        self.assertEqual(
            payload['player']['scouting_reports'][1]['report'],
            {'status': 'pending'},
        )

    def test_external_player_steam_id_falls_back_to_player_id(self):
        response = self.client.get(
            '/api/v1/external/player?steamid=p1&season=last',
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['player']['player_id'], 'p1')

    def test_external_player_can_be_queried_by_live_room_id(self):
        response = self.client.get(
            '/api/v1/external/player?room_id=DOUYU_731778&season=season-one',
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['lookup'], {'type': 'room_id', 'value': 'DOUYU_731778'})
        self.assertEqual(payload['player']['player_id'], 'p1')
        self.assertEqual(payload['player']['avg_rating'], 1.0)
        self.assertEqual(payload['player']['avg_pw_rating'], 1.0)

        # The platform prefix keeps identical room numbers unambiguous.
        response = self.client.get(
            '/api/v1/external/player?room_id=huya_731778&season=current-season',
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['data']['player']['player_id'], 'p2')

    def test_external_player_requires_exactly_one_identifier(self):
        response = self.client.get('/api/v1/external/player?season=all', headers=self.auth)
        self.assertEqual(response.status_code, 400)

        response = self.client.get(
            '/api/v1/external/player?steam_id=steam-p1&room_id=DOUYU_731778&season=all',
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 400)

    def test_external_player_returns_404_for_unknown_identifier(self):
        response = self.client.get(
            '/api/v1/external/player?room_id=missing&season=all',
            headers=self.auth,
        )
        self.assertEqual(response.status_code, 404)

    def _login_admin(self):
        with self.client.session_transaction() as session:
            session['admin_user'] = 'admin'

    def test_admin_can_bind_and_unbind_child_account(self):
        self._login_admin()
        Player.create(player_id='group-main', nickname='账号组主玩家', in_library=True)
        Player.create(player_id='group-child', nickname='账号组子账号', steam_id='steam-child')
        try:
            bound = self.client.post('/api/admin/player-accounts/bind', json={
                'parent_player_id': 'group-main',
                'child_player_ids': ['group-child'],
            })
            self.assertEqual(bound.status_code, 200)
            self.assertEqual(
                Player.get(Player.player_id == 'group-child').parent_player_id,
                'group-main',
            )

            listing = self.client.get('/api/admin/players?q=group-main').get_json()['data']
            self.assertEqual(listing['players'][0]['child_accounts'][0]['player_id'], 'group-child')

            unbound = self.client.delete('/api/admin/player-accounts/group-child')
            self.assertEqual(unbound.status_code, 200)
            self.assertIsNone(Player.get(Player.player_id == 'group-child').parent_player_id)

            create_match_player('group-conflict', 'group-main', 'season-two')
            create_match_player('group-conflict', 'group-child', 'season-two')
            conflict = self.client.post('/api/admin/player-accounts/bind', json={
                'parent_player_id': 'group-main',
                'child_player_ids': ['group-child'],
            })
            self.assertEqual(conflict.status_code, 409)
            self.assertEqual(
                conflict.get_json()['data']['conflict_match_ids'],
                ['group-conflict'],
            )
        finally:
            MatchPlayer.delete().where(MatchPlayer.match_id == 'group-conflict').execute()
            Player.delete().where(Player.player_id.in_(['group-main', 'group-child'])).execute()

    def test_account_group_mutations_require_admin(self):
        bind = self.client.post('/api/admin/player-accounts/bind', json={
            'parent_player_id': 'p1',
            'child_player_ids': ['p2'],
        })
        unbind = self.client.delete('/api/admin/player-accounts/p2')

        self.assertEqual(bind.status_code, 401)
        self.assertEqual(unbind.status_code, 401)

    def test_admin_can_keep_existing_wanmei_avatar(self):
        self._login_admin()
        Player.create(
            player_id='avatar-wanmei', nickname='完美头像玩家',
            avatar='https://img.wmpvp.com/wanmei.png',
            wanmei_avatar='https://img.wmpvp.com/wanmei.png',
            avatar_source='wanmei', in_library=True,
        )
        response = self.client.get(
            '/api/admin/player/save?player_id=avatar-wanmei&nickname=test'
            '&avatar_source=wanmei&live_platform=DOUYU&live_room=',
        )
        self.assertEqual(response.status_code, 200)
        player = Player.get(Player.player_id == 'avatar-wanmei')
        self.assertEqual(player.avatar_source, 'wanmei')
        self.assertEqual(player.avatar, 'https://img.wmpvp.com/wanmei.png')

    def test_admin_can_select_steam_avatar(self):
        self._login_admin()
        Player.create(
            player_id='avatar-steam', nickname='Steam 头像玩家',
            avatar='https://img.wmpvp.com/wanmei.png',
            wanmei_avatar='https://img.wmpvp.com/wanmei.png',
            avatar_source='wanmei', in_library=True,
        )
        with patch('app.fetch_steam_avatar', return_value={
            'steam_id': '76561198205495787',
            'avatar': 'https://avatars.fastly.steamstatic.com/example_full.jpg',
        }):
            response = self.client.get(
                '/api/admin/player/save?player_id=avatar-steam&nickname=test'
                '&steam_id=76561198205495787&avatar_source=steam'
                '&live_platform=DOUYU&live_room=',
            )
        self.assertEqual(response.status_code, 200)
        player = Player.get(Player.player_id == 'avatar-steam')
        self.assertEqual(player.avatar_source, 'steam')
        self.assertEqual(player.avatar, 'https://avatars.fastly.steamstatic.com/example_full.jpg')
        self.assertEqual(player.wanmei_avatar, 'https://img.wmpvp.com/wanmei.png')

    def test_admin_can_select_douyu_avatar_from_full_url(self):
        self._login_admin()
        Player.create(
            player_id='avatar-douyu', nickname='斗鱼头像玩家',
            avatar='https://img.wmpvp.com/wanmei.png',
            wanmei_avatar='https://img.wmpvp.com/wanmei.png',
            avatar_source='wanmei', in_library=True,
        )
        with patch('app.fetch_live_avatar', return_value='https://apic.douyucdn.cn/avatar.jpg') as fetch:
            response = self.client.get(
                '/api/admin/player/save?player_id=avatar-douyu&nickname=test'
                '&avatar_source=live&live_platform=DOUYU'
                '&live_room=https%3A%2F%2Fwww.douyu.com%2F2602307%3Ffrom%3Dtest',
            )
        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with('DOUYU', '2602307')
        player = Player.get(Player.player_id == 'avatar-douyu')
        self.assertEqual(player.avatar_source, 'live')
        self.assertEqual(player.avatar, 'https://apic.douyucdn.cn/avatar.jpg')
        self.assertEqual(player.live_url, 'https://www.douyu.com/2602307')

    def test_admin_portrait_upload_transform_and_delete(self):
        player_id = 'portrait-admin-test'
        Player.create(player_id=player_id, nickname='人物照片测试', in_library=True)
        try:
            unauthorized = self.client.post(
                f'/api/admin/player/{player_id}/portrait',
                data={'portrait': (io.BytesIO(b'image'), 'portrait.jpg')},
                content_type='multipart/form-data',
            )
            self.assertEqual(unauthorized.status_code, 401)

            self._login_admin()
            with patch('app.save_portrait', return_value=(
                'portrait-original.jpg', 'portrait-cutout.webp',
            )):
                response = self.client.post(
                    f'/api/admin/player/{player_id}/portrait',
                    data={
                        'portrait': (io.BytesIO(b'image'), 'portrait.jpg'),
                        'scale': '1.35', 'offset_x': '12', 'offset_y': '-8',
                    },
                    content_type='multipart/form-data',
                )
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()['data']['portrait']
            self.assertEqual(payload['url'], '/media/player-portraits/portrait-cutout.webp')
            self.assertEqual(payload['scale'], 1.35)
            self.assertEqual(payload['offset_x'], 12.0)
            self.assertEqual(payload['offset_y'], -8.0)

            response = self.client.patch(
                f'/api/admin/player/{player_id}/portrait',
                json={'scale': 9, 'offset_x': -90, 'offset_y': 90},
            )
            self.assertEqual(response.status_code, 200)
            payload = response.get_json()['data']['portrait']
            self.assertEqual(payload['scale'], 2.2)
            self.assertEqual(payload['offset_x'], -50.0)
            self.assertEqual(payload['offset_y'], 50.0)

            with patch('app.delete_portrait_files') as remove_files:
                response = self.client.delete(f'/api/admin/player/{player_id}/portrait')
            self.assertEqual(response.status_code, 200)
            remove_files.assert_called_once_with(
                'portrait-original.jpg', 'portrait-cutout.webp',
            )
            player = Player.get(Player.player_id == player_id)
            self.assertIsNone(player.portrait_cutout)
        finally:
            Player.delete().where(Player.player_id == player_id).execute()

    def test_public_players_exposes_only_safe_portrait_payload(self):
        cache.clear()
        (Player.update(
            portrait_original='private-original.jpg',
            portrait_cutout='versioned-cutout.webp',
            portrait_scale=1.25,
            portrait_offset_x=8,
            portrait_offset_y=-6,
        ).where(Player.player_id == 'p1').execute())
        try:
            response = self.client.get('/api/v1/players?cup=season-two')
            self.assertEqual(response.status_code, 200)
            players = response.get_json()['data']['players']
            player = next(item for item in players if item['player_id'] == 'p1')
            self.assertEqual(player['portrait'], {
                'url': '/media/player-portraits/versioned-cutout.webp',
                'scale': 1.25,
                'offset_x': 8.0,
                'offset_y': -6.0,
            })
            for item in players:
                for private_field in (
                    'portrait_original', 'portrait_cutout', 'portrait_scale',
                    'portrait_offset_x', 'portrait_offset_y',
                ):
                    self.assertNotIn(private_field, item)
        finally:
            (Player.update(
                portrait_original=None,
                portrait_cutout=None,
                portrait_scale=1.0,
                portrait_offset_x=0.0,
                portrait_offset_y=0.0,
            ).where(Player.player_id == 'p1').execute())
            cache.clear()

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
        self.assertEqual(payload['players'][0]['avg_pw_rating'], 1.0)

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
        self.assertEqual(records[0]['round_count'], 20)
        self.assertEqual(records[0]['kast_ratio'], 0.75)
        matchups = response.get_json()['data']['kill_matchups']
        self.assertEqual(matchups, [])

    def test_kill_matchups_use_reciprocal_ratio_and_minimum_sample(self):
        cup_name = 'matchup-ratio-season'
        try:
            create_match_player(
                'matchup-a', 'p1', cup_name,
                kill_map=json.dumps({'p2': 7, 'low-sample': 5}),
            )
            create_match_player(
                'matchup-b', 'p2', cup_name,
                kill_map=json.dumps({'p1': 2}),
            )

            self.assertEqual(MatchPlayer.get_player_kill_matchups(cup_name, 'p1'), [{
                'player_id': 'p2',
                'nickname': '选手二',
                'kills': 7,
                'deaths': 2,
                'encounters': 9,
                'kill_death_ratio': 3.5,
            }])
        finally:
            (MatchPlayer
             .delete()
             .where(MatchPlayer.cup_name == cup_name)
             .execute())

    def test_kill_matchups_include_opponents_with_only_deaths(self):
        cup_name = 'death-only-matchup-season'
        try:
            create_match_player(
                'matchup-victim', 'p1', cup_name,
                kill_map=json.dumps({}),
            )
            create_match_player(
                'matchup-attacker', 'p2', cup_name,
                kill_map=json.dumps({'p1': 6}),
            )

            self.assertEqual(MatchPlayer.get_player_kill_matchups(cup_name, 'p1'), [{
                'player_id': 'p2',
                'nickname': '选手二',
                'kills': 0,
                'deaths': 6,
                'encounters': 6,
                'kill_death_ratio': 0.0,
            }])
        finally:
            (MatchPlayer
             .delete()
             .where(MatchPlayer.cup_name == cup_name)
             .execute())

    def test_public_match_detail_only_exposes_approved_matches(self):
        response = self.client.get('/api/v1/match?cup=season-two&match_id=m2')
        self.assertEqual(response.status_code, 200)
        detail = response.get_json()['data']
        self.assertEqual(detail['map_name'], '炼狱小镇')
        self.assertEqual(detail['team1_name'], 'Alpha')
        self.assertEqual(detail['players'][0]['alias_name'], 'One')
        self.assertEqual(detail['players'][0]['kast_ratio'], 0.75)

        hidden = MatchSelection.create(
            match_id='m-hidden', season_cup_name='season-two', status='rejected',
            source_type='custom', play_day='20250101', roster_hit_count=0,
        )
        try:
            response = self.client.get('/api/v1/match?cup=season-two&match_id=m-hidden')
            self.assertEqual(response.status_code, 404)
        finally:
            hidden.delete_instance()

    def test_public_match_detail_includes_player_matchup_matrix(self):
        cup = 'season-two'
        match_id = 'm-matchup-matrix'
        Match.create(
            match_id=match_id, map_name='炙热沙城', map_name_en='de_dust2',
            start_time=datetime(2025, 2, 4, 20, 0, 0),
            end_time=datetime(2025, 2, 4, 20, 40, 0), duration=2400,
            win_team=1, team1_name='Alpha', team1_score=13, team1_half_score=7,
            team2_name='Bravo', team2_score=10, team2_half_score=5,
            game_mode='MR12', cup_name=cup, play_day='20250101',
        )
        MatchSelection.create(
            match_id=match_id, season_cup_name=cup, status='approved',
            source_type='custom', play_day='20250101', roster_hit_count=2,
        )
        create_match_player(
            match_id, 'p1', cup, team=1, kill_map=json.dumps({'p2': 7, 'outsider': 9}),
        )
        create_match_player(
            match_id, 'p2', cup, team=2, kill_map=json.dumps({'p1': 4}),
        )
        try:
            response = self.client.get(f'/api/v1/match?cup={cup}&match_id={match_id}')
            self.assertEqual(response.status_code, 200)
            matrix = response.get_json()['data']['matchup_matrix']
            self.assertEqual(matrix['p1']['p2'], {'kills': 7, 'deaths': 4})
            self.assertEqual(matrix['p2']['p1'], {'kills': 4, 'deaths': 7})
            self.assertNotIn('outsider', matrix['p1'])
            self.assertNotIn('p1', matrix['p1'])
        finally:
            MatchPlayer.delete().where(MatchPlayer.match_id == match_id).execute()
            MatchSelection.delete().where(MatchSelection.match_id == match_id).execute()
            Match.delete().where(Match.match_id == match_id).execute()

    def test_public_match_detail_uses_player_profile_avatar(self):
        cup = 'season-two'
        match_id = 'm-avatar-overlay'
        profile_avatar = 'https://avatars.fastly.steamstatic.com/profile_full.jpg'
        snapshot_avatar = 'https://img.wmpvp.com/match-snapshot.png'
        Player.create(
            player_id='p-avatar-overlay', nickname='头像覆盖选手',
            alias_name='Overlay', avatar=profile_avatar,
            wanmei_avatar=snapshot_avatar, avatar_source='steam',
            in_library=True,
        )
        Player.create(
            player_id='p-avatar-fallback', nickname='无档案头像选手',
            alias_name='Fallback', in_library=True,
        )
        Match.create(
            match_id=match_id, map_name='荒漠迷城', map_name_en='de_mirage',
            start_time=datetime(2025, 2, 3, 21, 0, 0),
            end_time=datetime(2025, 2, 3, 21, 40, 0), duration=2400,
            win_team=1, team1_name='Alpha', team1_score=13, team1_half_score=7,
            team2_name='Bravo', team2_score=8, team2_half_score=5,
            game_mode='MR12', cup_name=cup, play_day='20250101',
        )
        MatchSelection.create(
            match_id=match_id, season_cup_name=cup, status='approved',
            source_type='custom', play_day='20250101', roster_hit_count=2,
        )
        create_match_player(
            match_id, 'p-avatar-overlay', cup, avatar=snapshot_avatar,
            team=1, game_count=21, kast=16,
        )
        create_match_player(
            match_id, 'p-avatar-fallback', cup,
            avatar='https://img.wmpvp.com/fallback.png',
            team=2, game_count=21, kast=10,
        )
        try:
            response = self.client.get(f'/api/v1/match?cup={cup}&match_id={match_id}')
            self.assertEqual(response.status_code, 200)
            players = {
                player['player_id']: player
                for player in response.get_json()['data']['players']
            }
            self.assertEqual(players['p-avatar-overlay']['avatar'], profile_avatar)
            self.assertEqual(
                players['p-avatar-fallback']['avatar'],
                'https://img.wmpvp.com/fallback.png',
            )
        finally:
            MatchPlayer.delete().where(MatchPlayer.match_id == match_id).execute()
            MatchSelection.delete().where(MatchSelection.match_id == match_id).execute()
            Match.delete().where(Match.match_id == match_id).execute()
            Player.delete().where(Player.player_id.in_([
                'p-avatar-overlay', 'p-avatar-fallback',
            ])).execute()

    def test_public_match_detail_validates_required_parameters(self):
        self.assertEqual(self.client.get('/api/v1/match?match_id=m2').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/match?cup=season-two').status_code, 400)

    def test_admin_match_list_exposes_exact_start_time(self):
        with self.client.session_transaction() as session:
            session['admin_user'] = 'admin'
        response = self.client.get(
            '/api/admin/selection/list?cup=season-two&status=approved',
        )
        self.assertEqual(response.status_code, 200)
        records = response.get_json()['data']['list']
        self.assertEqual(records[0]['start_time'], '2025-02-03T20:15:30')

    def test_admin_can_save_season_when_datetime_omits_zero_seconds(self):
        cup = 'season-minute-precision-test'
        self._login_admin()
        try:
            response = self.client.get('/api/admin/season/save', query_string={
                'cup': cup,
                'cup_alias': '整分时间测试',
                'start_date': '2026-09-01T02:00',
                'end_date': '2026-09-01T03:00',
                'status': 'archived',
            })

            self.assertEqual(response.status_code, 200)
            season = Season.get(Season.cup_name == cup)
            self.assertEqual(season.start_date, datetime(2026, 9, 1, 2, 0))
            self.assertEqual(season.end_date, datetime(2026, 9, 1, 3, 0))
        finally:
            Season.delete_with_related_data(cup)

    def test_admin_can_delete_season_and_related_data(self):
        cup = 'season-delete-test'
        match_id = 'm-delete-test'
        Season.create(
            cup_name=cup, cup_alias='待删除赛季', name='待删除赛季',
            start_date=datetime(2025, 1, 1), end_date=datetime(2025, 2, 1),
            status='archived', match_type='custom',
        )
        SeasonRoster.create(season_cup_name=cup, player_id='p1')
        Match.create(
            match_id=match_id, map_name='荒漠迷城', map_name_en='de_mirage',
            start_time=datetime(2025, 1, 2, 20), end_time=datetime(2025, 1, 2, 21),
            duration=3600, win_team=1, team1_name='Alpha', team1_score=13,
            team1_half_score=7, team2_name='Bravo', team2_score=8,
            team2_half_score=5, game_mode='MR12', cup_name=cup, play_day='20250102',
        )
        create_match_player(match_id, 'p1', cup)
        MatchSelection.create(
            match_id=match_id, season_cup_name=cup, status='approved',
            source_type='custom', play_day='20250102', roster_hit_count=1,
        )
        CupDayChampion.create(cup_name=cup, day='20250102')
        PlayerTitle.create(
            player_id='p1', cup_name=cup, play_day='20250102',
            title_name='测试称号', title_description='测试',
            title_category='achievement', title_type='positive',
        )
        Config.set_value(f'crawl_enabled:{cup}', '0')
        Config.set_value(f'crawl_status:{cup}', '{"state":"done"}')

        with self.client.session_transaction() as session:
            session['admin_user'] = 'admin'
        response = self.client.post('/api/admin/season/delete', json={'cup': cup})

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()['data']
        self.assertEqual(payload['message'], '赛季已删除')
        self.assertIsNone(Season.get_by_cup(cup))
        self.assertEqual(SeasonRoster.select().where(SeasonRoster.season_cup_name == cup).count(), 0)
        self.assertEqual(MatchSelection.select().where(MatchSelection.season_cup_name == cup).count(), 0)
        self.assertEqual(PlayerTitle.select().where(PlayerTitle.cup_name == cup).count(), 0)
        self.assertEqual(CupDayChampion.select().where(CupDayChampion.cup_name == cup).count(), 0)
        self.assertIsNone(Config.get_value(f'crawl_enabled:{cup}'))
        self.assertIsNone(Config.get_value(f'crawl_status:{cup}'))

        # Raw crawl data remains available for a future re-import, but no
        # longer contributes to this deleted season.
        self.assertIsNone(Match.get(Match.match_id == match_id).cup_name)
        self.assertIsNone(MatchPlayer.get(MatchPlayer.match_id == match_id).cup_name)

    def test_admin_delete_season_validates_auth_and_existence(self):
        response = self.client.post('/api/admin/season/delete', json={'cup': 'missing'})
        self.assertEqual(response.status_code, 401)

        with self.client.session_transaction() as session:
            session['admin_user'] = 'admin'
        response = self.client.post('/api/admin/season/delete', json={'cup': 'missing'})
        self.assertEqual(response.status_code, 404)

    def test_admin_cannot_delete_a_running_season(self):
        cup = 'season-running-delete-test'
        Season.create(
            cup_name=cup, cup_alias='采集中赛季', name='采集中赛季',
            start_date=datetime(2025, 1, 1), end_date=datetime(2099, 2, 1),
            status='active', match_type='custom',
        )
        set_crawl_status(
            cup,
            state='running',
            heartbeat_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        )
        try:
            with self.client.session_transaction() as session:
                session['admin_user'] = 'admin'
            response = self.client.post('/api/admin/season/delete', json={'cup': cup})
            self.assertEqual(response.status_code, 409)
            self.assertIsNotNone(Season.get_by_cup(cup))
        finally:
            Season.delete_with_related_data(cup)

    def test_public_cup_cache_hits_and_season_invalidation(self):
        cache.clear()
        path = '/api/v1/cup/season-two'
        first = self.client.get(path)
        second = self.client.get(path)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.headers.get('X-Cache'), 'MISS')
        self.assertEqual(second.headers.get('X-Cache'), 'HIT')

        invalidate_season('season-two', external=False)
        third = self.client.get(path)
        self.assertEqual(third.status_code, 200)
        self.assertEqual(third.headers.get('X-Cache'), 'MISS')

    def test_external_auth_is_checked_before_response_cache(self):
        cache.clear()
        path = '/api/v1/external/players?season=last'
        populated = self.client.get(path, headers=self.auth)
        self.assertEqual(populated.status_code, 200)
        self.assertEqual(populated.headers.get('X-Cache'), 'MISS')

        unauthorized = self.client.get(path)
        self.assertEqual(unauthorized.status_code, 401)

    def test_cup_cold_query_count_does_not_scale_per_player(self):
        cache.clear()
        selects = []
        connection = db.connection()
        connection.set_trace_callback(
            lambda sql: selects.append(sql)
            if sql.lstrip().upper().startswith('SELECT') else None
        )
        try:
            response = self.client.get('/api/v1/cup/season-two')
        finally:
            connection.set_trace_callback(None)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(selects), 15, '\n'.join(selects))


if __name__ == '__main__':
    unittest.main()
