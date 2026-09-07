import os
import tempfile
import unittest
from unittest.mock import patch

from seo_service import SeoPage, build_page, render_index, robots_text


class SeoServiceTest(unittest.TestCase):
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


if __name__ == '__main__':
    unittest.main()
