from flask import Flask, render_template

from config import CUP_NAME
from database import MatchPlayer

app = Flask(__name__)

# Path 参数 cup 、day
@app.route('/<string:cup>/<string:day>/')
def index(cup, day):
    if cup is None:
        cup = CUP_NAME

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
    } for player in players}

    player_data = []
    for player_id,player in players_map.items():
        print(player)

        d = MatchPlayer.get_match_exploit(cup, player_id, day)
        if d:
            player.update(d)

        player_data.append(player)

    # 根据rating排序
    player_data.sort(key=lambda x: x.get('avg_pw_rating', 0), reverse=True)

    return render_template('index.html', players=player_data, cup=cup, day=day)


if __name__ == '__main__':
    app.run(debug=True, port=5001)
