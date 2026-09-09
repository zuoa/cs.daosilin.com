import os
import tempfile
import unittest
from unittest.mock import patch

from seo_service import SeoPage, build_page, render_index, robots_text


class SeoServiceTest(unittest.TestCase):
    def test_homepage_declares_stable_favicon_urls(self):
        index_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 'web', 'index.html',
        )
        with open(index_path, encoding='utf-8') as index_file:
            source = index_file.read()

        self.assertIn('rel="icon" href="/favicon.ico"', source)
        self.assertIn('href="/favicon-96x96.png"', source)
        self.assertIn('rel="apple-touch-icon"', source)

    def test_robots_points_to_real_sitemap_and_blocks_api_routes(self):
        body = robots_text()
        self.assertIn('Sitemap: https://cs.daosilin.com/sitemap.xml', body)
        self.assertIn('Disallow: /api/', body)
        # HTML routes stay crawlable so bots can observe their noindex header.
        self.assertNotIn('Disallow: /admin/', body)

    def test_render_index_adds_unique_metadata_and_snapshot(self):
        source = '''<!doctype html><html><head>
          <meta name="description" content="old" />
          <meta name="twitter:title" content="熊掌CS Major" />
          <meta name="twitter:description" content="old twitter" />
          <meta name="robots" content="index,follow" />
          <title>old</title></head><body><div id="app"></div></body></html>'''
        page = SeoPage(
            title='选手 A 数据',
            description='选手 A 的 Rating 和 K/D 数据。',
            canonical_path='/player/a/cup/',
            body_html='<main><h1>选手 A</h1></main>',
        )
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', delete=False) as index_file:
            index_file.write(source)
            index_path = index_file.name
        try:
            result = render_index(index_path, page)
        finally:
            os.unlink(index_path)
        self.assertIn('<title>选手 A 数据</title>', result)
        self.assertIn('<meta name="twitter:title" content="选手 A 数据" />', result)
        self.assertIn(
            '<meta name="twitter:description" content="选手 A 的 Rating 和 K/D 数据。" />',
            result,
        )
        self.assertEqual(result.count('name="twitter:title"'), 1)
        self.assertNotIn('<meta name="twitter:title" content="熊掌CS Major"', result)
        self.assertIn('https://cs.daosilin.com/player/a/cup/', result)
        self.assertEqual(result.count('rel="canonical"'), 1)
        self.assertIn('<div id="app"><main><h1>选手 A</h1></main></div>', result)

    @patch('seo_service.Season.get_by_cup', return_value=None)
    def test_unknown_season_is_a_real_missing_page(self, _get_by_cup):
        self.assertIsNone(build_page('not-a-season'))

    def test_all_admin_views_are_noindex_pages(self):
        for path in ('admin/login', 'admin/season', 'admin/drafts', 'admin/players',
                     'admin/honours', 'admin/tasks', 'admin/feedback', 'admin/settings'):
            with self.subTest(path=path):
                page = build_page(path)
                self.assertFalse(page.indexable)
                self.assertEqual(page.canonical_path, f'/{path}')

    @patch('seo_service.Season.get_by_cup', return_value={'cup_name': 'cup'})
    @patch('seo_service._season_days', return_value=['20260907'])
    def test_unknown_day_is_a_real_missing_page(self, _days, _get_by_cup):
        self.assertIsNone(build_page('cup/19990101'))

    @patch('seo_service.build_cup_players', return_value=([], []))
    @patch('seo_service._season_days', return_value=[])
    @patch('seo_service.Season.get_by_cup', return_value={
        'cup_name': 'cup', 'cup_alias': '测试赛季',
    })
    def test_season_page_still_resolves(self, _get_by_cup, _days, _players):
        page = build_page('cup')

        self.assertEqual(page.canonical_path, '/cup/')
        self.assertIn('测试赛季', page.title)

    @patch('seo_service.season_list_payload', return_value=[{
        'cup_name': 'cup', 'cup_alias': '测试赛季', 'status': 'active',
        'start_date': '2026-09-01T00:00:00', 'end_date': '2026-09-09T00:00:00',
        'match_count': 12, 'day_count': 4,
    }])
    def test_home_snapshot_contains_season_status_and_counts(self, _seasons):
        page = build_page('')

        self.assertIn('测试赛季', page.body_html)
        self.assertIn('进行中', page.body_html)
        self.assertIn('<dd>12</dd>', page.body_html)
        self.assertIn('<dd>4</dd>', page.body_html)

    @patch('seo_service.build_cup_players', return_value=([{
        'player_id': 'p/1', 'alias_name': 'Alpha <script>',
        'avg_pw_rating': 1.56, 'kd_ratio': 1.25, 'win_rate': 0.625,
        'match_count': 8, 'avg_adpr': 92.4, 'total_mvp': 3,
        'is_champion': True,
        'titles': [{
            'title_name': '火力核心',
            'title_description': 'Rating 排名前列 <img src=x>',
        }],
        'community_rating': {
            'status': 'formed', 'score': 4.25, 'label': '顶级',
            'total_votes': 12, 'minimum_votes': 5,
        },
    }], []))
    @patch('seo_service._season_days', return_value=['20260907'])
    @patch('seo_service.Season.get_by_cup', return_value={
        'cup_name': 'cup', 'cup_alias': '测试赛季',
    })
    def test_season_snapshot_contains_rank_metrics_titles_and_safe_links(
        self, _get_by_cup, _days, _players,
    ):
        page = build_page('cup')

        self.assertIn('#1', page.body_html)
        self.assertIn('<dd>1.56</dd>', page.body_html)
        self.assertIn('<dd>1.25</dd>', page.body_html)
        self.assertIn('<dd>62.5%</dd>', page.body_html)
        self.assertIn('火力核心', page.body_html)
        self.assertIn('冠军', page.body_html)
        self.assertIn('/player/p%2F1/cup/', page.body_html)
        self.assertIn('Alpha &lt;script&gt;', page.body_html)
        self.assertNotIn('<img src=x>', page.body_html)

    @patch('seo_service.build_cup_players', return_value=([{
        'player_id': 'p1', 'alias_name': 'Alpha',
        'community_rating': {
            'status': 'formed', 'score': 4.25, 'label': '顶级',
            'total_votes': 12, 'minimum_votes': 5,
        },
    }, {
        'player_id': 'p2', 'alias_name': 'Bravo',
        'community_rating': {
            'status': 'collecting', 'score': None, 'label': None,
            'total_votes': 3, 'minimum_votes': 5,
        },
    }], []))
    @patch('seo_service._season_days', return_value=[])
    @patch('seo_service.Season.get_by_cup', return_value={
        'cup_name': 'cup', 'cup_alias': '测试赛季',
    })
    def test_community_snapshot_contains_score_votes_and_pending_players(
        self, _get_by_cup, _days, _players,
    ):
        page = build_page('cup/community')

        self.assertIn('加权评分 4.25 · 12 票', page.body_html)
        self.assertIn('等待成榜', page.body_html)
        self.assertIn('3/5 票', page.body_html)

    @patch('seo_service.player_detail_payload', return_value=({
        'canonical_player_id': 'p1',
        'player': {'player_id': 'p1', 'alias_name': 'Alpha <script>'},
        'player_data': {
            'avg_pw_rating': 1.67, 'kd_ratio': 1.4, 'win_rate': 0.75,
            'match_count': 4, 'total_kills': 56, 'total_deaths': 40,
            'total_assists': 12, 'avg_adpr': 98.5, 'total_mvp': 6,
        },
        'titles': [{
            'title_name': '输出机器', 'title_description': '稳定高效',
        }],
        'trophy_history': [{
            'trophy': 'champion', 'day': '20260907', 'team_name': 'A 队',
        }],
        'map_stats': [{
            'map_name': '炼狱小镇', 'match_count': 2, 'avg_rating': 1.7,
            'win_rate': 50, 'kd_ratio': 1.5,
        }],
        'match_records': [{
            'play_day': '20260907', 'map_name': '炼狱小镇', 'win': 1,
            'pw_rating': 1.8, 'kill': 20, 'death': 10, 'assist': 5,
        }],
        'player_rankings': {'avg_pw_rating': 2, 'total_kills': 3},
        'season_summary': {
            'status': 'completed', 'headline': '稳定火力点',
            'overview': '表现稳定 <b>可靠</b>', 'strength': '火力',
            'weakness': '样本较少', 'style': '稳健',
        },
        'cup_alias': '测试赛季', 'cup_days': ['20260907'],
    }, None))
    @patch('seo_service._season_days', return_value=['20260907'])
    @patch('seo_service.Season.get_by_cup', return_value={
        'cup_name': 'cup', 'cup_alias': '测试赛季',
    })
    def test_player_snapshot_contains_full_public_profile_and_escapes_content(
        self, _get_by_cup, _days, _payload,
    ):
        page = build_page('player/p1/cup')

        self.assertIn('Alpha &lt;script&gt;', page.body_html)
        self.assertIn('<dd>1.67</dd>', page.body_html)
        self.assertIn('输出机器', page.body_html)
        self.assertIn('稳定火力点', page.body_html)
        self.assertIn('赛季第 2 名', page.body_html)
        self.assertIn('炼狱小镇', page.body_html)
        self.assertIn('近期比赛', page.body_html)
        self.assertIn('表现稳定 &lt;b&gt;可靠&lt;/b&gt;', page.body_html)
        self.assertNotIn('<b>可靠</b>', page.body_html)

    @patch('seo_service._honours_page', return_value=SeoPage(
        title='赛季荣誉展', description='荣誉', canonical_path='/cup/honours',
    ))
    @patch('seo_service.Season.get_by_cup', return_value={'cup_name': 'cup'})
    def test_honours_route_is_resolved_before_a_day(self, _get_by_cup, honours_page):
        page = build_page('cup/honours')

        self.assertEqual(page.canonical_path, '/cup/honours')
        honours_page.assert_called_once()


if __name__ == '__main__':
    unittest.main()
