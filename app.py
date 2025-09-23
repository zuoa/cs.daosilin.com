from flask import Flask, render_template
from flask_caching import Cache

import title_service
from ajlog import logger
from config import CUP_NAME
from database import MatchPlayer, Player, CupDayChampion, create_tables, Config, PlayerTitle
from title_service import title_service

app = Flask(__name__)

cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)


@app.route('/')
def index_redirect():
    return index_cup_day(CUP_NAME, None)


@app.route('/<string:cup>/')
@app.route('/<string:cup>/<string:day>/')
@cache.cached(timeout=60)
def index_cup_day(cup, day=None):
    if cup is None:
        cup = CUP_NAME

    all_players = Player.get_all()
    all_players_map = {player["player_id"]: player for player in all_players}

    day_champion = CupDayChampion.get_champion_by_cup_and_day(cup, day)
    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))

    filter_params = {
        'cup_name': cup,
    }
    if day is not None:
        filter_params['play_day'] = day
    players = MatchPlayer.filter_records(**filter_params)
    players_map = {player["player_id"]: {
        "nickname": player["nickname"],
        "avatar": player["avatar"],
        "player_id": player["player_id"],
        "alias_name": all_players_map.get(player["player_id"], {}).get("alias_name", ""),
        "is_champion": player["player_id"] in day_champion.get("champion_team_player_ids", '').split(',') if day_champion else False,
        "is_runner_up": player["player_id"] in day_champion.get("runner_up_team_player_ids", '').split(',') if day_champion else False,
    } for player in players}

    player_data = []
    for player_id, player in players_map.items():
        d = MatchPlayer.get_match_exploit(cup, player_id, day)
        if d:
            player.update(d)

        for champion in all_champions:
            if player_id in champion.get("champion_team_player_ids", '').split(','):
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('champion_team_name'),
                    'trophy': 'champion',
                })
            if player_id in champion.get("runner_up_team_player_ids", '').split(','):
                player.setdefault('trophy_history', []).append({
                    'day': champion.get('day'),
                    'team_name': champion.get('runner_up_team_name'),
                    'trophy': 'runner_up',
                })

        # 获取玩家称号
        titles = PlayerTitle.get_player_titles(player_id, cup, day)
        player['titles'] = titles

        player_data.append(player)

    # 根据rating排序
    player_data.sort(key=lambda x: x.get('avg_pw_rating', 0), reverse=True)

    cup_days = MatchPlayer.get_cup_day_set()

    last_crawl_time = Config.get_value("last_crawl_time")

    return render_template('index.html', players=player_data, cup=cup, day=day, cup_days=cup_days, current_day=day, last_crawl_time=last_crawl_time)


@app.cli.command("init-db")
def init_db():
    """Initialize the database tables"""
    try:
        create_tables()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败: {str(e)}")


if __name__ == '__main__':
    app.run(debug=True, port=5001)
