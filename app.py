from flask import Flask, render_template, request
from flask_caching import Cache

import title_service
from ajlog import logger
from champion_service import judge_champion
from config import CUP_NAME, AUTH_CODE
from database import MatchPlayer, Player, CupDayChampion, create_tables, Config, PlayerTitle
from title_service import title_service
from utils import success, error

app = Flask(__name__)

cache = Cache(config={'CACHE_TYPE': 'SimpleCache'})
cache.init_app(app)


@app.route('/')
def index_redirect():
    return index_cup_day(CUP_NAME, None)


@app.route('/api/v1/players')
@cache.cached(timeout=120)
def api_players():
    cup = request.args.get('cup')
    if cup is None:
        cup = CUP_NAME

    auth = request.args.get('auth')
    if auth != AUTH_CODE:
        return error(403, "无权限访问")

    day = request.args.get('day')

    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))

    all_players = Player.get_all()
    for i in range(len(all_players)):
        player = all_players[i]
        player_id = player.get('player_id')
        d = MatchPlayer.get_match_exploit(cup, player_id, day)
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
    last_crawl_time = Config.get_value("last_crawl_time")
    return success({"players": all_players, "cache_time": last_crawl_time})


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
        "team_name": player.get("team_name", ""),
        "is_champion": player["player_id"] in day_champion.get("champion_team_player_ids", '').split(
            ',') if day_champion else False,
        "is_runner_up": player["player_id"] in day_champion.get("runner_up_team_player_ids", '').split(
            ',') if day_champion else False,
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

    return render_template('index.html', players=player_data, cup=cup, day=day, cup_days=cup_days, current_day=day,
                           last_crawl_time=last_crawl_time)


@app.route('/player/<string:player_id>/')
@app.route('/player/<string:player_id>/<string:cup>/')
@app.route('/player/<string:player_id>/<string:cup>/<string:day>/')
@cache.cached(timeout=60)
def player_detail(player_id, cup=None, day=None):
    """选手详情页"""
    if cup is None:
        cup = CUP_NAME

    # 获取选手基本信息
    player = Player.get_by_id(player_id)
    if not player:
        return error(404, "选手不存在")

    # 获取选手比赛数据
    player_data = MatchPlayer.get_match_exploit(cup, player_id, day)
    if not player_data:
        return error(404, "该选手在此杯赛/日期下无数据")

    # 获取选手称号
    titles = PlayerTitle.get_player_titles(player_id, cup, day)

    # 获取选手历史奖杯
    all_champions = CupDayChampion.filter_records(**{'cup_name': cup})
    all_champions.sort(key=lambda champion: champion.get('day', ''))
    
    trophy_history = []
    for champion in all_champions:
        if player_id in champion.get("champion_team_player_ids", '').split(','):
            trophy_history.append({
                'day': champion.get('day'),
                'team_name': champion.get('champion_team_name'),
                'trophy': 'champion',
            })
        if player_id in champion.get("runner_up_team_player_ids", '').split(','):
            trophy_history.append({
                'day': champion.get('day'),
                'team_name': champion.get('runner_up_team_name'),
                'trophy': 'runner_up',
            })

    # 获取选手历史数据（用于图表展示）
    historical_data = []
    cup_days = MatchPlayer.get_cup_day_set()
    
    for historical_day in cup_days:
        day_data = MatchPlayer.get_match_exploit(cup, player_id, historical_day)
        if day_data:
            historical_data.append({
                'day': historical_day,
                'data': day_data
            })

    # 获取所有选手数据用于排名比较
    all_players = Player.get_all()
    all_players_data = []
    for p in all_players:
        p_data = MatchPlayer.get_match_exploit(cup, p["player_id"], day)
        if p_data:
            p_data['player_id'] = p["player_id"]
            p_data['nickname'] = p["nickname"]
            all_players_data.append(p_data)

    # 计算排名
    player_rankings = {}
    ranking_fields = ['avg_pw_rating', 'total_kills', 'kd_ratio', 'win_rate', 'avg_adpr', 'total_mvp']
    
    for field in ranking_fields:
        if field in player_data:
            sorted_players = sorted(all_players_data, key=lambda x: x.get(field, 0), reverse=True)
            try:
                rank = next(i for i, p in enumerate(sorted_players) if p['player_id'] == player_id) + 1
                player_rankings[field] = rank
            except StopIteration:
                player_rankings[field] = len(all_players_data)

    # 获取选手地图统计数据
    map_stats = MatchPlayer.get_player_map_stats(cup, player_id, day)

    # 获取杯赛信息
    cup_days = MatchPlayer.get_cup_day_set()
    last_crawl_time = Config.get_value("last_crawl_time")

    return render_template('player_detail.html', 
                         player=player, 
                         player_data=player_data,
                         titles=titles,
                         trophy_history=trophy_history,
                         historical_data=historical_data,
                         player_rankings=player_rankings,
                         map_stats=map_stats,
                         cup=cup, 
                         day=day,
                         cup_days=cup_days,
                         last_crawl_time=last_crawl_time)


@app.route('/api/admin/champion/judge')
def api_admin_champion_judge():
    auth = request.args.get('auth')
    if auth != AUTH_CODE:
        return error(403, "无权限访问")

    day = request.args.get('day')
    if day is None:
        return error(400, "参数 day 不能为空")

    cup_name = request.args.get('cup')
    if cup_name is None:
        cup_name = CUP_NAME

    try:
        judge_champion(cup_name, day)
    except Exception as e:
        logger.error(f"计算冠军和亚军失败: {str(e)}")

    return success("计算冠军和亚军任务已触发")

@app.route('/api/admin/title/refresh')
def api_admin_title_refresh():
    auth = request.args.get('auth')
    if auth != AUTH_CODE:
        return error(403, "无权限访问")

    day = request.args.get('day')
    cup_name = request.args.get('cup')
    if cup_name is None:
        cup_name = CUP_NAME
        
    try:
        # 计算整个杯赛的称号
        is_success = title_service.calculate_and_save_titles(cup_name)
        if is_success:
            logger.info(f"成功计算 {cup_name} 的称号")
        else:
            logger.error(f"计算 {cup_name} 称号失败")

        is_success = title_service.calculate_and_save_titles(cup_name, day)
        if is_success:
            logger.info(f"成功计算 {cup_name} {day} 的称号")
        else:
            logger.error(f"计算 {cup_name} {day} 称号失败")

    except Exception as e:
        logger.error(f"计算称号失败: {str(e)}")

    return success("计算称号任务已触发")


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
