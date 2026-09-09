"""Search-engine friendly HTML, route validation, and sitemap generation."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from html import escape
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

from peewee import fn

from config import SITE_NAME, SITE_URL
from database import MatchPlayer, Player, Season
from honours_service import build_season_honours


@dataclass
class SeoPage:
    title: str
    description: str
    canonical_path: str
    body_html: str = ''
    indexable: bool = True
    structured_data: list = field(default_factory=list)


_ADMIN_PATHS = {
    'admin/login',
    'admin/season',
    'admin/players',
    'admin/tasks',
    'admin/feedback',
    'admin/settings',
}


def _url_path(*parts, trailing=False):
    path = '/' + '/'.join(quote(str(part), safe='') for part in parts)
    return f'{path}/' if trailing else path


def _absolute(path):
    return f'{SITE_URL}{path}'


def _display_name(season):
    return (
        season.get('cup_alias') or season.get('name')
        or season.get('cup_name') or ''
    )


def _date(value):
    if not value:
        return ''
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value).replace('T', ' ')[:10]


def _season_days(cup):
    return [str(day) for day in MatchPlayer.get_cup_day_set(cup) if day]


def _season_players(cup, day=None):
    query = MatchPlayer.select(MatchPlayer.player_id, MatchPlayer.nickname).where(
        MatchPlayer.cup_name == cup
    )
    if day:
        query = query.where(MatchPlayer.play_day == day)
    account_map = Player.account_map()
    profiles = {
        str(row.player_id): row
        for row in Player.select().where(Player.parent_player_id.is_null(True))
    }
    players = {}
    for row in query.distinct():
        player_id = account_map.get(str(row.player_id), str(row.player_id))
        profile = profiles.get(player_id)
        if not profile:
            continue
        players[player_id] = (
            profile.alias_name or profile.nickname or row.nickname or player_id
        )
    return sorted(players.items(), key=lambda item: item[1].casefold())


def _breadcrumbs(items):
    return {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {
                '@type': 'ListItem',
                'position': index,
                'name': name,
                'item': _absolute(path),
            }
            for index, (name, path) in enumerate(items, start=1)
        ],
    }


def _home_page():
    seasons = list(Season.select().order_by(Season.start_date.desc()))
    links = ''.join(
        '<li><a href="{path}">{name}</a><span>{dates}</span></li>'.format(
            path=escape(_url_path(row.cup_name, trailing=True), quote=True),
            name=escape(row.cup_alias or row.name or row.cup_name),
            dates=escape(f'{_date(row.start_date)} — {_date(row.end_date)}'),
        )
        for row in seasons
    )
    body = f'''<div class="public-site home-page seo-snapshot">
      <main>
        <section class="home-hero"><div class="hero-copy">
          <h1>读懂每一局，不止看比分。</h1>
          <p>围绕选手、赛季与比赛日组织的 CS2 赛事数据档案，查看 Rating、K/D、称号与冠军记录。</p>
        </div></section>
        <section id="seasons" class="season-section"><h2>赛季数据</h2><ul>{links}</ul></section>
      </main>
    </div>'''
    description = '熊掌 CS Major 提供 CS2 自定义赛事数据、选手 Rating、K/D、比赛记录、称号与冠军统计。'
    return SeoPage(
        title=f'{SITE_NAME}｜CS2 赛事数据、选手 Rating 与战绩',
        description=description,
        canonical_path='/',
        body_html=body,
        structured_data=[{
            '@context': 'https://schema.org',
            '@type': 'WebSite',
            'name': SITE_NAME,
            'url': _absolute('/'),
            'description': description,
            'inLanguage': 'zh-CN',
        }],
    )


def _season_page(season, day=None, community=False):
    cup = str(season['cup_name'])
    name = _display_name(season)
    days = _season_days(cup)
    if day and day not in days:
        return None
    canonical_path = (
        _url_path(cup, 'community') if community
        else _url_path(cup, *([day] if day else []), trailing=True)
    )
    players = _season_players(cup, day)
    player_links = ''.join(
        '<li><a href="{path}">{name}</a></li>'.format(
            path=escape(
                _url_path('player', player_id, cup, *([day] if day else []), trailing=True),
                quote=True,
            ),
            name=escape(player_name),
        )
        for player_id, player_name in players
    )
    day_links = ''.join(
        '<li><a href="{path}">{day}</a></li>'.format(
            path=escape(_url_path(cup, value, trailing=True), quote=True),
            day=escape(value),
        )
        for value in days
    )
    if community:
        heading = f'{name}从夯到拉排名'
        summary = f'{name}选手社区票选与加权排名，共 {len(players)} 名选手。'
    elif day:
        heading = f'{name} · {day}'
        summary = f'查看 {name} {day} 当日选手 Rating、K/D 与比赛表现，共 {len(players)} 名选手。'
    else:
        heading = name
        summary = (
            f'查看 {name} 赛季选手排名、Rating、K/D、比赛记录与冠军统计，'
            f'共 {len(players)} 名选手。'
        )
    body = f'''<div class="public-site season-page seo-snapshot">
      <main>
        <section class="season-hero"><h1>{escape(heading)}</h1><p>{escape(summary)}</p></section>
        <nav aria-label="比赛日"><a href="{escape(_url_path(cup, trailing=True), quote=True)}">赛季总览</a><ul>{day_links}</ul></nav>
        <section><h2>{'社区票选选手' if community else '选手榜单'}</h2><ul>{player_links}</ul></section>
      </main>
    </div>'''
    title_suffix = '社区票选排名' if community else (f'{day} 当日数据' if day else '选手排名与战绩')
    breadcrumb_items = [(SITE_NAME, '/'), (name, _url_path(cup, trailing=True))]
    if community:
        breadcrumb_items.append(('社区票选排名', canonical_path))
    elif day:
        breadcrumb_items.append((day, canonical_path))
    return SeoPage(
        title=f'{name} {title_suffix}｜{SITE_NAME}',
        description=summary,
        canonical_path=canonical_path,
        body_html=body,
        structured_data=[_breadcrumbs(breadcrumb_items)],
    )


def _honours_page(season):
    cup = str(season['cup_name'])
    name = _display_name(season)
    payload = build_season_honours(cup)
    canonical_path = _url_path(cup, 'honours')
    award_items = []
    for award in payload.get('awards') or []:
        winners = '、'.join(
            f"{entry['position']}. {entry['name']}（{entry['display_value']}）"
            for entry in award.get('entries') or []
        ) or '样本积累中'
        award_items.append(
            '<article id="honour-{key}"><h2>{title}</h2><p>{description}</p>'
            '<p>{winners}</p><small>{method}</small></article>'.format(
                key=escape(str(award.get('key') or ''), quote=True),
                title=escape(str(award.get('title') or '')),
                description=escape(str(award.get('description') or '')),
                winners=escape(winners),
                method=escape(str(award.get('method') or '')),
            )
        )
    description = (
        f'{name} CS2 赛季荣誉展：冠军、亚军、决赛次数、首轮出局、'
        'Rating 波动、社区评分反差与对局专项数据 TOP3。'
    )
    body = f'''<div class="public-site honours-page seo-snapshot"><main>
      <nav><a href="{escape(_url_path(cup, trailing=True), quote=True)}">返回 {escape(name)} 赛季数据</a></nav>
      <section><h1>{escape(name)} 荣誉展</h1><p>{escape(description)}</p></section>
      <section>{''.join(award_items)}</section>
    </main></div>'''
    return SeoPage(
        title=f'{name} 赛季荣誉展与趣味数据 TOP3｜{SITE_NAME}',
        description=description,
        canonical_path=canonical_path,
        body_html=body,
        structured_data=[_breadcrumbs([
            (SITE_NAME, '/'),
            (name, _url_path(cup, trailing=True)),
            ('赛季荣誉展', canonical_path),
        ])],
    )


def _player_page(player_id, season, day=None):
    cup = str(season['cup_name'])
    days = _season_days(cup)
    if day and day not in days:
        return None
    canonical_id = Player.canonical_player_id(player_id)
    profile = Player.get_or_none(Player.player_id == canonical_id)
    if not profile:
        return None
    account_ids = Player.account_ids(canonical_id)
    filters = [MatchPlayer.cup_name == cup, MatchPlayer.player_id.in_(account_ids)]
    if day:
        filters.append(MatchPlayer.play_day == day)
    stats = (MatchPlayer
             .select(
                 fn.COUNT(MatchPlayer.id).alias('records'),
                 fn.SUM(MatchPlayer.kill).alias('kills'),
                 fn.SUM(MatchPlayer.death).alias('deaths'),
                 fn.SUM(MatchPlayer.assist).alias('assists'),
                 fn.AVG(MatchPlayer.pw_rating).alias('rating'),
             )
             .where(*filters)
             .dicts()
             .get())
    if not stats.get('records'):
        return None
    if canonical_id != str(player_id):
        return SeoPage('', '', _url_path(
            'player', canonical_id, cup, *([day] if day else []), trailing=True,
        ))
    name = profile.alias_name or profile.nickname or canonical_id
    season_name = _display_name(season)
    canonical_path = _url_path(
        'player', canonical_id, cup, *([day] if day else []), trailing=True,
    )
    kills = int(stats.get('kills') or 0)
    deaths = int(stats.get('deaths') or 0)
    assists = int(stats.get('assists') or 0)
    rating = float(stats.get('rating') or 0)
    kd = kills / deaths if deaths else kills
    scope = f'{day} 当日' if day else '赛季'
    description = (
        f'{name} 在 {season_name} {scope}的 CS2 数据：Rating {rating:.2f}、'
        f'K/D {kd:.2f}、{kills} 击杀、{deaths} 死亡与 {assists} 助攻。'
    )
    body = f'''<div class="public-site player-page seo-snapshot">
      <main>
        <nav><a href="{escape(_url_path(cup, *([day] if day else []), trailing=True), quote=True)}">返回 {escape(season_name)} 榜单</a></nav>
        <article><h1>{escape(name)}</h1><p>{escape(description)}</p>
          <dl><dt>Rating</dt><dd>{rating:.2f}</dd><dt>K/D</dt><dd>{kd:.2f}</dd><dt>击杀</dt><dd>{kills}</dd><dt>死亡</dt><dd>{deaths}</dd><dt>助攻</dt><dd>{assists}</dd></dl>
        </article>
      </main>
    </div>'''
    title_scope = f'{day} 当日数据' if day else f'{season_name} 赛季数据'
    return SeoPage(
        title=f'{name}｜{title_scope}、Rating 与 K/D｜{SITE_NAME}',
        description=description,
        canonical_path=canonical_path,
        body_html=body,
        structured_data=[
            _breadcrumbs([
                (SITE_NAME, '/'),
                (season_name, _url_path(cup, trailing=True)),
                (name, canonical_path),
            ]),
            {
                '@context': 'https://schema.org',
                '@type': 'ProfilePage',
                'url': _absolute(canonical_path),
                'name': f'{name} - {season_name}',
                'mainEntity': {
                    '@type': 'Person',
                    'name': name,
                    'identifier': canonical_id,
                },
            },
        ],
    )


def _noindex_page(path, title):
    return SeoPage(
        title=f'{title} · {SITE_NAME}',
        description=f'{SITE_NAME} {title}',
        canonical_path=path,
        indexable=False,
    )


def build_page(spa_path):
    """Resolve a SPA path to a validated SEO page, or None for a real 404."""
    clean = (spa_path or '').strip('/')
    if not clean:
        return _home_page()
    if clean in _ADMIN_PATHS:
        return _noindex_page('/' + clean, '管理后台')
    if clean == 'draft':
        return _noindex_page('/draft', '选人结果')

    parts = clean.split('/')
    if any(not part for part in parts):
        return None
    if parts[0] == 'broadcast' and len(parts) == 2:
        season = Season.get_by_cup(parts[1])
        return _noindex_page(_url_path(*parts), '赛事直播数据') if season else None
    if parts[0] == 'compare' and len(parts) in (2, 3):
        season = Season.get_by_cup(parts[1])
        if not season or (len(parts) == 3 and parts[2] not in _season_days(parts[1])):
            return None
        return _noindex_page(_url_path(*parts), '选手对比')
    if parts[0] == 'player':
        if len(parts) not in (3, 4):
            return None
        season = Season.get_by_cup(parts[2])
        return _player_page(parts[1], season, parts[3] if len(parts) == 4 else None) if season else None

    season = Season.get_by_cup(parts[0])
    if not season:
        return None
    if len(parts) == 2 and parts[1] == 'community':
        return _season_page(season, community=True)
    if len(parts) == 2 and parts[1] == 'honours':
        return _honours_page(season)
    if len(parts) in (1, 2):
        return _season_page(season, parts[1] if len(parts) == 2 else None)
    return None


def _set_meta(html, name, content):
    tag = f'<meta name="{name}" content="{escape(content, quote=True)}" />'
    pattern = re.compile(rf'<meta\s+name=["\']{re.escape(name)}["\'][^>]*>', re.I)
    if pattern.search(html):
        return pattern.sub(lambda _match: tag, html, count=1)
    return html.replace('</head>', f'    {tag}\n  </head>')


def render_index(index_path, page):
    with open(index_path, encoding='utf-8') as index_file:
        html = index_file.read()
    title = escape(page.title, quote=False)
    html = re.sub(
        r'<title>.*?</title>', lambda _match: f'<title>{title}</title>',
        html, count=1, flags=re.I | re.S,
    )
    html = _set_meta(html, 'description', page.description)
    html = _set_meta(html, 'twitter:title', page.title)
    html = _set_meta(html, 'twitter:description', page.description)
    html = _set_meta(html, 'robots', 'index,follow' if page.indexable else 'noindex,follow')

    canonical = _absolute(page.canonical_path)
    extra = [
        f'<link rel="canonical" href="{escape(canonical, quote=True)}" />',
        f'<meta property="og:site_name" content="{escape(SITE_NAME, quote=True)}" />',
        f'<meta property="og:type" content="website" />',
        f'<meta property="og:title" content="{escape(page.title, quote=True)}" />',
        f'<meta property="og:description" content="{escape(page.description, quote=True)}" />',
        f'<meta property="og:url" content="{escape(canonical, quote=True)}" />',
        '<meta name="twitter:card" content="summary" />',
    ]
    for data in page.structured_data:
        payload = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
        payload = payload.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        extra.append(f'<script type="application/ld+json">{payload}</script>')
    html = html.replace('</head>', '    ' + '\n    '.join(extra) + '\n  </head>')
    if page.body_html:
        html = re.sub(
            r'<div\s+id=["\']app["\']\s*>\s*</div>',
            lambda _match: f'<div id="app">{page.body_html}</div>',
            html,
            count=1,
            flags=re.I,
        )
    return html


def robots_text():
    return '\n'.join([
        'User-agent: *',
        'Allow: /',
        'Disallow: /api/',
        f'Sitemap: {_absolute("/sitemap.xml")}',
        '',
    ])


def build_sitemap():
    seasons = list(Season.select())
    season_map = {str(row.cup_name): row for row in seasons}
    valid_days = {
        cup: set(_season_days(cup))
        for cup in season_map
    }
    latest_cup = {
        str(row.cup_name): row.lastmod
        for row in (MatchPlayer
                    .select(MatchPlayer.cup_name, fn.MAX(MatchPlayer.updated_at).alias('lastmod'))
                    .where(MatchPlayer.cup_name.is_null(False))
                    .group_by(MatchPlayer.cup_name))
    }
    raw_rows = list(MatchPlayer
                    .select(MatchPlayer.cup_name, MatchPlayer.play_day, MatchPlayer.player_id)
                    .where(MatchPlayer.cup_name.is_null(False))
                    .distinct())
    account_map = Player.account_map()
    profile_ids = {
        str(row.player_id)
        for row in Player.select(Player.player_id).where(Player.parent_player_id.is_null(True))
    }

    entries = {}

    def add(path, modified=''):
        value = _date(modified)
        if path not in entries or value > entries[path]:
            entries[path] = value

    site_modified = max((_date(value) for value in latest_cup.values()), default='')
    add('/', site_modified)
    for cup, season in season_map.items():
        modified = latest_cup.get(cup) or season.updated_at
        add(_url_path(cup, trailing=True), modified)
        add(_url_path(cup, 'community'), modified)
        add(_url_path(cup, 'honours'), modified)

    daily_entries = []
    for row in raw_rows:
        cup = str(row.cup_name or '')
        if cup not in season_map:
            continue
        modified = latest_cup.get(cup) or season_map[cup].updated_at
        day = str(row.play_day or '')
        canonical_id = account_map.get(str(row.player_id), str(row.player_id))
        if day and day in valid_days[cup]:
            add(_url_path(cup, day, trailing=True), modified)
        if canonical_id not in profile_ids:
            continue
        add(_url_path('player', canonical_id, cup, trailing=True), modified)
        if day and day in valid_days[cup]:
            daily_entries.append((
                _url_path('player', canonical_id, cup, day, trailing=True), modified,
            ))

    # Keep one sitemap below Google's 50,000 URL limit. Daily player filters are
    # the first URLs omitted if the site eventually grows beyond that boundary.
    for path, modified in daily_entries:
        if len(entries) >= 49_999:
            break
        add(path, modified)

    urls = []
    for path, modified in sorted(entries.items()):
        lastmod = f'<lastmod>{xml_escape(modified)}</lastmod>' if modified else ''
        urls.append(f'<url><loc>{xml_escape(_absolute(path))}</loc>{lastmod}</url>')
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        + ''.join(urls)
        + '</urlset>\n'
    )


def render_not_found():
    name = escape(SITE_NAME)
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
      <meta name="robots" content="noindex,follow"><meta name="viewport" content="width=device-width,initial-scale=1">
      <title>页面不存在 · {name}</title></head><body><main>
      <h1>页面不存在</h1><p>该赛季、比赛日或选手页面不存在。</p><p><a href="/">返回数据首页</a></p>
      </main></body></html>'''
