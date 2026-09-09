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
        self.assertIn('https://cs.daosilin.com/player/a/cup/', result)
        self.assertEqual(result.count('rel="canonical"'), 1)
        self.assertIn('<div id="app"><main><h1>选手 A</h1></main></div>', result)

    @patch('seo_service.Season.get_by_cup', return_value=None)
    def test_unknown_season_is_a_real_missing_page(self, _get_by_cup):
        self.assertIsNone(build_page('not-a-season'))

    @patch('seo_service.Season.get_by_cup', return_value={'cup_name': 'cup'})
    @patch('seo_service._season_days', return_value=['20260907'])
    def test_unknown_day_is_a_real_missing_page(self, _days, _get_by_cup):
        self.assertIsNone(build_page('cup/19990101'))

    @patch('seo_service._season_players', return_value=[])
    @patch('seo_service._season_days', return_value=[])
    @patch('seo_service.Season.get_by_cup', return_value={
        'cup_name': 'cup', 'cup_alias': '测试赛季',
    })
    def test_season_page_still_resolves(self, _get_by_cup, _days, _players):
        page = build_page('cup')

        self.assertEqual(page.canonical_path, '/cup/')
        self.assertIn('测试赛季', page.title)

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
