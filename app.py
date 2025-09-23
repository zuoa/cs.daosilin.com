from flask import Flask, render_template
from flask_caching import Cache

from config import CUP_NAME
from database import MatchPlayer, Player, CupDayChampion

app = Flask(__name__)

cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)


# Path 参数 cup 、day
@app.route('/<string:cup>/<string:day>/')
@cache.cached(timeout=60)
def index(cup, day):
    if cup is None:
        cup = CUP_NAME

    all_players = Player.get_all()
    all_players_map = {player["player_id"]: player for player in all_players}

    day_champion = CupDayChampion.get_champion_by_cup_and_day(cup, day)

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
        print(player)

        d = MatchPlayer.get_match_exploit(cup, player_id, day)
        if d:
            player.update(d)

        player_data.append(player)

    # 根据rating排序
    player_data.sort(key=lambda x: x.get('avg_pw_rating', 0), reverse=True)

    cup_days = MatchPlayer.get_cup_day_set()

    return render_template('index.html', players=player_data, cup=cup, day=day, cup_days=cup_days, current_day=day)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
