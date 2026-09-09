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
from public_data_service import (
    build_cup_players,
    player_detail_payload,
    season_list_payload,
)


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
    'admin/drafts',
    'admin/players',
    'admin/honours',
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


def _player_name(player):
    return str(
        player.get('alias_name') or player.get('nickname')
        or player.get('player_id') or ''
    )


def _number(value, digits=2):
    try:
        return f'{float(value or 0):.{digits}f}'
    except (TypeError, ValueError):
        return f'{0:.{digits}f}'


def _percent(value, *, ratio=True):
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        number = 0
    if ratio:
        number *= 100
    return f'{number:.1f}%'


def _title_list(titles):
    seen = set()
    items = []
    for title in titles or []:
        name = str(title.get('title_name') or '')
        if not name or name in seen:
            continue
        seen.add(name)
        description = str(title.get('title_description') or '')
        items.append(
            '<li><strong>{name}</strong>{description}</li>'.format(
                name=escape(name),
                description=(f'<span>{escape(description)}</span>' if description else ''),
            )
        )
    return ''.join(items)


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
    seasons = season_list_payload()
    cards = ''.join(
        '<li><article><h3><a href="{path}">{name}</a></h3>'
        '<p>{status} · {dates}</p><dl><dt>比赛</dt><dd>{matches}</dd>'
        '<dt>比赛日</dt><dd>{days}</dd></dl></article></li>'.format(
            path=escape(_url_path(season.get('cup_name'), trailing=True), quote=True),
            name=escape(_display_name(season)),
            status='进行中' if season.get('status') == 'active' else '已归档',
            dates=escape(
                f"{_date(season.get('start_date'))} — {_date(season.get('end_date'))}"
            ),
            matches=int(season.get('match_count') or 0),
            days=int(season.get('day_count') or 0),
        )
        for season in seasons
    )
    body = f'''<div class="public-site home-page seo-snapshot">
      <main>
        <section class="home-hero"><div class="hero-copy">
          <h1>读懂每一局，不止看比分。</h1>
          <p>围绕选手、赛季与比赛日组织的 CS2 赛事数据档案，查看 Rating、K/D、称号与冠军记录。</p>
        </div></section>
        <section id="seasons" class="season-section"><h2>赛季数据</h2><ul>{cards}</ul></section>
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
    players, _cup_days = build_cup_players(cup, day)
    canonical_path = (
        _url_path(cup, 'community') if community
        else _url_path(cup, *([day] if day else []), trailing=True)
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
        formed = [
            player for player in players
            if (player.get('community_rating') or {}).get('status') == 'formed'
        ]
        formed.sort(key=lambda player: (
            -float(player['community_rating'].get('score') or 0),
            -int(player['community_rating'].get('total_votes') or 0),
            _player_name(player).casefold(),
        ))
        ranked = [(index, player) for index, player in enumerate(formed, start=1)]
        tier_sections = []
        for label in ('夯', '顶级', '人上人', 'NPC', '拉完了'):
            entries = ''.join(
                '<li value="{rank}"><a href="{path}">{name}</a>'
                '<span>加权评分 {score} · {votes} 票</span></li>'.format(
                    rank=rank,
                    path=escape(_url_path(
                        'player', player.get('player_id'), cup, trailing=True,
                    ), quote=True),
                    name=escape(_player_name(player)),
                    score=_number(player['community_rating'].get('score')),
                    votes=int(player['community_rating'].get('total_votes') or 0),
                )
                for rank, player in ranked
                if player['community_rating'].get('label') == label
            )
            tier_sections.append(
                f'<section><h2>{label}</h2><ol>{entries}</ol></section>'
            )
        pending = [player for player in players if player not in formed]
        pending_items = ''.join(
            '<li><a href="{path}">{name}</a><span>{votes}/{minimum} 票</span></li>'.format(
                path=escape(_url_path(
                    'player', player.get('player_id'), cup, trailing=True,
                ), quote=True),
                name=escape(_player_name(player)),
                votes=int((player.get('community_rating') or {}).get('total_votes') or 0),
                minimum=int((player.get('community_rating') or {}).get('minimum_votes') or 5),
            )
            for player in pending
        )
        ranking_html = ''.join(tier_sections)
        if pending_items:
            ranking_html += f'<section><h2>等待成榜</h2><ul>{pending_items}</ul></section>'
        summary = (
            f'{name}选手社区票选与加权排名，共 {len(players)} 名选手，'
            f'{len(formed)} 名已经成榜。'
        )
    elif day:
        heading = f'{name} · {day}'
        summary = f'查看 {name} {day} 当日选手 Rating、K/D 与比赛表现，共 {len(players)} 名选手。'
    else:
        heading = name
        summary = (
            f'查看 {name} 赛季选手排名、Rating、K/D、比赛记录与冠军统计，'
            f'共 {len(players)} 名选手。'
        )
    if not community:
        player_rows = []
        for rank, player in enumerate(players, start=1):
            player_path = _url_path(
                'player', player.get('player_id'), cup,
                *([day] if day else []), trailing=True,
            )
            honours = []
            if player.get('is_champion'):
                honours.append('冠军')
            if player.get('is_runner_up'):
                honours.append('亚军')
            titles = _title_list(player.get('titles'))
            player_rows.append(
                '<li><article><h3><span>#{rank}</span> '
                '<a href="{path}">{name}</a>{honours}</h3>'
                '<dl><dt>Rating</dt><dd>{rating}</dd><dt>K/D</dt><dd>{kd}</dd>'
                '<dt>胜率</dt><dd>{win_rate}</dd><dt>比赛</dt><dd>{matches}</dd>'
                '<dt>ADR</dt><dd>{adr}</dd><dt>MVP</dt><dd>{mvp}</dd></dl>'
                '{titles}</article></li>'.format(
                    rank=rank,
                    path=escape(player_path, quote=True),
                    name=escape(_player_name(player)),
                    honours=(f'<small>{escape("、".join(honours))}</small>' if honours else ''),
                    rating=_number(player.get('avg_pw_rating')),
                    kd=_number(player.get('kd_ratio')),
                    win_rate=_percent(player.get('win_rate')),
                    matches=int(player.get('match_count') or 0),
                    adr=_number(player.get('avg_adpr')),
                    mvp=int(player.get('total_mvp') or 0),
                    titles=(f'<h4>数据称号</h4><ul>{titles}</ul>' if titles else ''),
                )
            )
        ranking_html = f'<section><h2>选手榜单</h2><ol>{"".join(player_rows)}</ol></section>'
    body = f'''<div class="public-site season-page seo-snapshot">
      <main>
        <section class="season-hero"><h1>{escape(heading)}</h1><p>{escape(summary)}</p></section>
        <nav aria-label="比赛日"><a href="{escape(_url_path(cup, trailing=True), quote=True)}">赛季总览</a><ul>{day_links}</ul></nav>
        {ranking_html}
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
    payload, error = player_detail_payload(player_id, cup, day)
    if error or not payload:
        return None
    canonical_id = str(payload['canonical_player_id'])
    if canonical_id != str(player_id):
        return SeoPage('', '', _url_path(
            'player', canonical_id, cup, *([day] if day else []), trailing=True,
        ))
    profile = payload.get('player') or {}
    stats = payload.get('player_data') or {}
    name = _player_name({**profile, 'player_id': canonical_id})
    season_name = payload.get('cup_alias') or _display_name(season)
    canonical_path = _url_path(
        'player', canonical_id, cup, *([day] if day else []), trailing=True,
    )
    kills = int(stats.get('total_kills') or 0)
    deaths = int(stats.get('total_deaths') or 0)
    assists = int(stats.get('total_assists') or 0)
    rating = _number(stats.get('avg_pw_rating'))
    kd = _number(stats.get('kd_ratio'))
    scope = f'{day} 当日' if day else '赛季'
    description = (
        f'{name} 在 {season_name} {scope}的 CS2 数据：Rating {rating}、'
        f'K/D {kd}、{kills} 击杀、{deaths} 死亡与 {assists} 助攻。'
    )

    trophy_items = ''.join(
        '<li><strong>{trophy}</strong><span>{day} · {team}</span></li>'.format(
            trophy='冠军' if item.get('trophy') == 'champion' else '亚军',
            day=escape(str(item.get('day') or '')),
            team=escape(str(item.get('team_name') or '暂无队名')),
        )
        for item in payload.get('trophy_history') or []
    )
    title_items = _title_list(payload.get('titles'))
    map_items = ''.join(
        '<li><article><h3>{name}</h3><dl><dt>比赛</dt><dd>{matches}</dd>'
        '<dt>Rating</dt><dd>{rating}</dd><dt>胜率</dt><dd>{win_rate}</dd>'
        '<dt>K/D</dt><dd>{kd}</dd></dl></article></li>'.format(
            name=escape(str(item.get('map_name') or item.get('map_name_en') or '未知地图')),
            matches=int(item.get('match_count') or 0),
            rating=_number(item.get('avg_rating')),
            win_rate=_percent(item.get('win_rate'), ratio=False),
            kd=_number(item.get('kd_ratio')),
        )
        for item in (payload.get('map_stats') or [])[:6]
    )
    match_items = ''.join(
        '<li><article><h3>{day} · {map_name}</h3><p>{result}</p>'
        '<dl><dt>Rating</dt><dd>{rating}</dd><dt>K/D/A</dt>'
        '<dd>{kills}/{deaths}/{assists}</dd></dl></article></li>'.format(
            day=escape(str(item.get('play_day') or '')),
            map_name=escape(str(item.get('map_name') or item.get('map_name_en') or '未知地图')),
            result='胜利' if item.get('win') else '失利',
            rating=_number(item.get('pw_rating')),
            kills=int(item.get('kill') or 0),
            deaths=int(item.get('death') or 0),
            assists=int(item.get('assist') or 0),
        )
        for item in (payload.get('match_records') or [])[:10]
    )
    summary = payload.get('season_summary') or {}
    summary_html = ''
    if summary.get('status') == 'completed':
        points = ''.join(
            f'<div><dt>{label}</dt><dd>{escape(str(summary.get(key) or ""))}</dd></div>'
            for key, label in (
                ('strength', '优势'), ('weakness', '观察项'), ('style', '打法画像'),
            )
            if summary.get(key)
        )
        summary_html = (
            '<section><h2>{headline}</h2><p>{overview}</p><dl>{points}</dl></section>'.format(
                headline=escape(str(summary.get('headline') or '赛季球探报告')),
                overview=escape(str(summary.get('overview') or '')),
                points=points,
            )
        )
    ranking_labels = {
        'avg_pw_rating': 'Rating',
        'total_kills': '总击杀',
        'kd_ratio': 'K/D',
        'win_rate': '胜率',
        'avg_adpr': 'ADR',
        'total_mvp': 'MVP',
    }
    ranking_items = ''.join(
        f'<li><span>{label}</span><strong>赛季第 {int(rank)} 名</strong></li>'
        for field, label in ranking_labels.items()
        for rank in [(payload.get('player_rankings') or {}).get(field)]
        if rank
    )
    day_links = ''.join(
        '<li><a href="{path}">{day}</a></li>'.format(
            path=escape(_url_path('player', canonical_id, cup, value, trailing=True), quote=True),
            day=escape(value),
        )
        for value in payload.get('cup_days') or []
    )
    body = f'''<div class="public-site player-page seo-snapshot">
      <main>
        <nav><a href="{escape(_url_path(cup, *([day] if day else []), trailing=True), quote=True)}">返回 {escape(season_name)} 榜单</a></nav>
        <article><h1>{escape(name)}</h1><p>{escape(description)}</p>
          <dl><dt>Rating</dt><dd>{rating}</dd><dt>K/D</dt><dd>{kd}</dd>
          <dt>胜率</dt><dd>{_percent(stats.get('win_rate'))}</dd>
          <dt>比赛</dt><dd>{int(stats.get('match_count') or 0)}</dd>
          <dt>击杀</dt><dd>{kills}</dd><dt>死亡</dt><dd>{deaths}</dd>
          <dt>助攻</dt><dd>{assists}</dd><dt>ADR</dt><dd>{_number(stats.get('avg_adpr'))}</dd>
          <dt>MVP</dt><dd>{int(stats.get('total_mvp') or 0)}</dd></dl>
        </article>
        {f'<section><h2>赛季荣誉</h2><ul>{trophy_items}</ul></section>' if trophy_items else ''}
        {f'<section><h2>{"当日画像" if day else "赛季画像"}</h2><ul>{title_items}</ul></section>' if title_items else ''}
        {f'<section><h2>赛季排名</h2><ul>{ranking_items}</ul></section>' if ranking_items else ''}
        {summary_html}
        <nav aria-label="选手比赛日"><a href="{escape(_url_path('player', canonical_id, cup, trailing=True), quote=True)}">赛季总览</a><ul>{day_links}</ul></nav>
        {f'<section><h2>地图表现</h2><ul>{map_items}</ul></section>' if map_items else ''}
        {f'<section><h2>近期比赛</h2><ol>{match_items}</ol></section>' if match_items else ''}
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
