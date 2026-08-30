import json
from collections import Counter
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import parse_qs, unquote, urlsplit

from peewee import *
from playhouse.db_url import connect

from ajlog import logger
from config import DB_PATH, DATABASE_URL, HISTORY_SQL_PATH


def _open_database():
    if DATABASE_URL:
        return connect(DATABASE_URL)
    return SqliteDatabase(DB_PATH)


db = _open_database()


def is_postgres() -> bool:
    return isinstance(db, PostgresqlDatabase)


class BaseModel(Model):
    """基础模型类"""
    id = AutoField(primary_key=True)
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        database = db

    def save(self, *args, **kwargs):
        self.updated_at = datetime.now()
        return super().save(*args, **kwargs)

    def to_dict(self) -> Dict[str, Any]:
        """将模型转换为字典"""
        return {
            field.name: getattr(self, field.name)
            for field in self._meta.fields.values()
        }


class CRUDMixin:
    """CRUD操作混入类"""

    @classmethod
    def create_record(cls, **kwargs) -> 'BaseModel':
        """创建记录"""
        try:
            return cls.create(**kwargs)
        except Exception as e:
            logger.error(f"创建记录失败: {str(e)}")
            raise

    @classmethod
    def get_by_id(cls, record_id: int) -> Optional['BaseModel']:
        """根据ID获取记录"""
        try:
            return cls.get_by_id(record_id)
        except cls.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"获取记录失败: {str(e)}")
            raise

    @classmethod
    def get_or_create(cls, **kwargs) -> tuple:
        """获取或创建记录"""
        try:
            return cls.get_or_create(**kwargs)
        except Exception as e:
            logger.error(f"获取或创建记录失败: {str(e)}")
            raise

    @classmethod
    def update_record(cls, record_id: int, **kwargs) -> int:
        """更新记录"""
        try:
            kwargs['updated_at'] = datetime.now()
            return cls.update(**kwargs).where(cls.id == record_id).execute()
        except Exception as e:
            logger.error(f"更新记录失败: {str(e)}")
            raise

    @classmethod
    def delete_record(cls, record_id: int) -> int:
        """删除记录"""
        try:
            return cls.delete().where(cls.id == record_id).execute()
        except Exception as e:
            logger.error(f"删除记录失败: {str(e)}")
            raise

    @classmethod
    def get_all(cls, limit: int = None, offset: int = None) -> List[Dict[str, Any]]:
        """获取所有记录"""
        try:
            query = cls.select()
            if limit:
                query = query.limit(limit)
            if offset:
                query = query.offset(offset)
            return list(query.dicts())
        except Exception as e:
            logger.error(f"获取记录列表失败: {str(e)}")
            raise

    @classmethod
    def count_records(cls) -> int:
        """统计记录数量"""
        try:
            return cls.select().count()
        except Exception as e:
            logger.error(f"统计记录失败: {str(e)}")
            raise

    @classmethod
    def filter_records(cls, **conditions) -> List[Dict[str, Any]]:
        """根据条件过滤记录"""
        try:
            query = cls.select()
            for field, value in conditions.items():
                if hasattr(cls, field):
                    query = query.where(getattr(cls, field) == value)
            return list(query.dicts())
        except Exception as e:
            logger.error(f"过滤记录失败: {str(e)}")
            raise


class Match(BaseModel, CRUDMixin):
    """比赛模型"""
    match_id = CharField(max_length=64, unique=True)  # 比赛唯一标识
    map_name = CharField(max_length=64)
    map_name_en = CharField(max_length=64)
    map_url = CharField(max_length=255, null=True)  # 地图图片URL
    map_logo = CharField(max_length=255, null=True)  # 地图Logo URL
    start_time = DateTimeField()  # 比赛开始时间
    end_time = DateTimeField()  # 比赛结束时间
    duration = DoubleField()
    win_team = IntegerField()
    team1_id = CharField(max_length=64, null=True)  # 队伍ID
    team1_name = CharField(max_length=64, null=True)
    team1_logo = CharField(max_length=255, null=True)  # 队
    team1_score = IntegerField()
    team1_half_score = IntegerField()
    team1_extra_score = IntegerField(null=True)
    team2_id = CharField(max_length=64, null=True)  # 队伍ID
    team2_name = CharField(max_length=64, null=True)
    team2_logo = CharField(max_length=255, null=True)  # 队
    team2_score = IntegerField()
    team2_half_score = IntegerField()
    team2_extra_score = IntegerField(null=True)
    game_mode = CharField(max_length=64)  # 比赛模式
    cup_name = CharField(max_length=128, null=True)  # 杯赛名称
    cup_logo = CharField(max_length=255, null=True)  # 杯赛Logo URL
    play_day = CharField(max_length=64, null=True)
    notes = TextField(null=True)  # 原始比赛详情，便于后续补字段与排查上游数据

    @classmethod
    def get_by_match_id(cls, match_id: str) -> Optional[Dict[str, Any]]:
        """获取用户最新的一条运动记录"""
        try:
            match = (cls.select()
                     .where(cls.match_id == match_id)
                     .limit(1)
                     .get())
            return match.to_dict()
        except cls.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"获取最新记录失败: {str(e)}")
            return None

    class Meta:
        table_name = 'match'


class Player(BaseModel, CRUDMixin):
    player_id = CharField(max_length=64, primary_key=True)  # 玩家唯一标识
    nickname = CharField(max_length=64)
    avatar = CharField(max_length=255, null=True)  # 头像URL
    avatar_source = CharField(max_length=16, default='wanmei')  # wanmei / steam / live
    wanmei_avatar = CharField(max_length=500, null=True)
    steam_avatar = CharField(max_length=500, null=True)
    live_avatar = CharField(max_length=500, null=True)
    alias_name = CharField(max_length=255, null=True)  # 别名，多个别名用逗号分隔
    steam_id = CharField(max_length=64, null=True)  # Steam ID
    live_url = CharField(max_length=500, null=True)  # 直播间 URL
    in_library = BooleanField(default=False)  # 是否计入玩家库（占比门槛只认库内）
    perfect_score = IntegerField(null=True)  # 完美平台当前天梯分
    perfect_level = CharField(max_length=16, null=True)  # S21+ 完美平台段位
    perfect_rank_updated_at = DateTimeField(null=True)  # 段位最近成功更新时间

    @staticmethod
    def live_room_id(live_url: str) -> str:
        """Build PLATFORM_ROOM from a configured live-stream URL."""
        value = (live_url or '').strip()
        if not value:
            return ''
        try:
            parsed = urlsplit(value)
        except ValueError:
            return ''

        hostname = (parsed.hostname or '').lower()
        platform_domains = (
            ('DOUYU', 'douyu.com'),
            ('HUYA', 'huya.com'),
            ('BILIBILI', 'live.bilibili.com'),
            ('DOUYIN', 'live.douyin.com'),
            ('KUAISHOU', 'live.kuaishou.com'),
            ('CC', 'cc.163.com'),
            ('YY', 'yy.com'),
            ('TWITCH', 'twitch.tv'),
        )
        platform = next((
            name for name, domain in platform_domains
            if hostname == domain or hostname.endswith(f'.{domain}')
        ), '')
        if not platform:
            return ''

        query = parse_qs(parsed.query)
        for key in ('room_id', 'roomid', 'room', 'id'):
            values = query.get(key) or []
            if values and values[0].strip():
                return f'{platform}_{values[0].strip()}'

        path_parts = [unquote(part).strip() for part in parsed.path.split('/') if part.strip()]
        return f'{platform}_{path_parts[-1]}' if path_parts else ''

    @classmethod
    def find_by_external_identifier(cls, steam_id: str = None,
                                    room_id: str = None) -> Optional['Player']:
        """Find one player by Steam ID or the room ID in their live URL."""
        steam_id = (steam_id or '').strip()
        room_id = (room_id or '').strip()
        if steam_id:
            # Historical data commonly stores the Steam64 ID as player_id.
            return (cls.select()
                    .where((cls.steam_id == steam_id) | (cls.player_id == steam_id))
                    .order_by(cls.updated_at.desc())
                    .first())
        if room_id:
            expected = room_id.casefold()
            for player in cls.select().where(cls.live_url.is_null(False)):
                if cls.live_room_id(player.live_url).casefold() == expected:
                    return player
        return None

    @classmethod
    def is_exist(cls, player_id: str) -> Optional[bool]:
        """获取用户最新的一条运动记录"""
        try:
            player = (cls.select()
                      .where(cls.player_id == player_id)
                      .limit(1)
                      .get())
            return True
        except cls.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"获取最新记录失败: {str(e)}")
            return False

    class Meta:
        table_name = 'player'

    @classmethod
    def get_library_ids(cls) -> List[str]:
        """库内玩家 player_id 列表"""
        try:
            query = cls.select(cls.player_id).where(cls.in_library == True)
            return [r.player_id for r in query]
        except Exception as e:
            logger.error(f"获取玩家库失败: {str(e)}")
            return []

    @classmethod
    def search_players(cls, q: str = None, in_library: Optional[bool] = None,
                       limit: int = 300) -> List[Dict[str, Any]]:
        """搜索玩家（ID / 昵称 / 别名）"""
        try:
            query = cls.select()
            if q:
                q = q.strip()
                if q:
                    query = query.where(
                        (cls.player_id.contains(q)) |
                        (cls.nickname.contains(q)) |
                        (cls.alias_name.contains(q))
                    )
            if in_library is not None:
                query = query.where(cls.in_library == bool(in_library))
            query = query.order_by(cls.in_library.desc(), cls.nickname.asc()).limit(limit)
            return list(query.dicts())
        except Exception as e:
            logger.error(f"搜索玩家失败: {str(e)}")
            return []

    @classmethod
    def ensure_library_player(cls, player_id: str, nickname: str = None) -> None:
        """确保玩家在库内（种子写入时调用）"""
        player_id = (player_id or '').strip()
        if not player_id:
            return
        existing = cls.get_or_none(cls.player_id == player_id)
        if existing is None:
            cls.create(
                player_id=player_id,
                nickname=nickname or player_id,
                in_library=True,
            )
        elif not existing.in_library:
            existing.in_library = True
            existing.save()


class Config(BaseModel, CRUDMixin):
    """全局配置模型"""
    key = CharField(max_length=64, unique=True)  # 配置键
    value = TextField(null=True)  # 配置值

    class Meta:
        table_name = 'config'

    @classmethod
    def get_value(cls, key: str) -> Optional[str]:
        """获取配置值"""
        try:
            config = cls.get(cls.key == key)
            return config.value
        except cls.DoesNotExist:
            return None

    @classmethod
    def set_value(cls, key: str, value: str) -> 'Config':
        """设置配置值"""
        try:
            config, created = cls.get_or_create(key=key)
            config.value = value
            config.save()
            return config
        except Exception as e:
            logger.error(f"设置配置值失败: {str(e)}")
            raise


class PlayerTitle(BaseModel, CRUDMixin):
    """玩家称号模型"""
    player_id = CharField(max_length=64)  # 玩家ID
    cup_name = CharField(max_length=128, null=True)  # 杯赛名称
    play_day = CharField(max_length=64, null=True)  # 比赛日期
    title_name = CharField(max_length=128)  # 称号名称
    title_description = TextField(null=True)  # 称号描述
    title_category = CharField(max_length=64)  # 称号分类
    title_type = CharField(max_length=32)  # 称号类型 (positive/negative/neutral)
    title_priority = IntegerField(default=1)  # 称号优先级
    title_score = DoubleField(default=0.0)  # 称号匹配分数
    is_active = BooleanField(default=True)  # 是否激活
    awarded_at = DateTimeField(default=datetime.now)  # 获得时间

    class Meta:
        table_name = 'player_title'
        indexes = (
            (('player_id', 'cup_name', 'play_day'), False),
        )

    @classmethod
    def get_player_titles(cls, player_id: str, cup_name: str = None, play_day: str = None) -> List[Dict[str, Any]]:
        """获取玩家称号"""
        try:
            query = cls.select().where(cls.player_id == player_id, cls.is_active == True)
            if cup_name:
                query = query.where(cls.cup_name == cup_name)
            if play_day:
                query = query.where(cls.play_day == play_day)
            
            query = query.order_by(cls.title_priority.desc(), cls.title_score.desc())
            return list(query.dicts())
        except Exception as e:
            logger.error(f"获取玩家称号失败: {str(e)}")
            return []

    @classmethod
    def update_player_titles(cls, player_id: str, cup_name: str, play_day: str, titles_data: List[Dict]) -> bool:
        """更新玩家称号"""
        try:
            # 先删除该玩家在指定杯赛和日期的旧称号
            cls.delete().where(
                cls.player_id == player_id,
                cls.cup_name == cup_name,
                cls.play_day == play_day
            ).execute()
            
            # 插入新称号
            for title_data in titles_data:
                cls.create(
                    player_id=player_id,
                    cup_name=cup_name,
                    play_day=play_day,
                    title_name=title_data['name'],
                    title_description=title_data['description'],
                    title_category=title_data['category'],
                    title_type=title_data['type'],
                    title_priority=title_data['priority'],
                    title_score=title_data['score']
                )
            
            return True
        except Exception as e:
            logger.error(f"更新玩家称号失败: {str(e)}")
            return False


class CupDayChampion(BaseModel, CRUDMixin):
    cup_name = CharField(max_length=128)  # 杯赛名称
    day = CharField(max_length=64)  # 日期
    champion_team_name = TextField(null=True)
    champion_team_player_ids = TextField(null=True)
    runner_up_team_name = TextField(null=True)
    runner_up_team_player_ids = TextField(null=True)

    @classmethod
    def is_exist(cls, cup_name: str, day: str) -> Optional[bool]:
        """获取用户最新的一条运动记录"""
        try:
            exist = (cls.select()
                     .where(cls.cup_name == cup_name, cls.day == day)
                     .limit(1)
                     .get())
            return True
        except cls.DoesNotExist:
            return False
        except Exception as e:
            return False

    class Meta:
        table_name = 'cup_day_champion'

        ## 联合主键
        indexes = (
            (('cup_name', 'day'), True),
        )

    @classmethod
    def get_champion_by_cup_and_day(cls, cup_name: str, day: str) -> Optional[Dict[str, Any]]:
        """根据杯赛名称和日期获取冠军信息"""
        try:
            record = (cls.select()
                      .where((cls.cup_name == cup_name) & (cls.day == day))
                      .get())
            return record.to_dict()
        except cls.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"获取冠军信息失败: {str(e)}")
            return None


class MatchPlayer(BaseModel, CRUDMixin):
    match_id = CharField(max_length=64)  # 比赛唯一标识
    player_id = CharField(max_length=64)  # 玩家唯一标识
    nickname = CharField(max_length=64)
    avatar = CharField(max_length=255, null=True)  # 头像URL
    team = IntegerField()  # 队伍编号
    kill = IntegerField()  # 击杀数
    bot_kill = IntegerField()  # 机器人击杀数
    neg_kill = IntegerField()  # 负击杀数
    handgun_kill = IntegerField()  # 手枪击杀数
    entry_kill = IntegerField()  # 首杀数
    awp_kill = IntegerField()  # AWP击杀数
    death = IntegerField()  # 死亡数
    entry_death = IntegerField()  # 首死数
    assist = IntegerField()  # 助攻数
    headshot = IntegerField()  # 爆头数
    headshot_ratio = DoubleField()  # 爆头率
    rating = DoubleField()  # 评分
    pw_rating = DoubleField()  # PWR评分
    damage = IntegerField()  # 伤害值
    item_throw = IntegerField()  # 投掷物使用数
    flash = IntegerField()  # 闪光弹使用数
    flash_teammate = IntegerField()  # 队友闪光数
    flash_success = IntegerField()  # 成功闪光数
    end_game = IntegerField()  # 结束游戏数
    mvp_value = IntegerField()  # MVP值
    score = IntegerField()  # 分数
    ban_type = IntegerField()  # 禁赛类型
    two_kill = IntegerField()  # 双杀数
    three_kill = IntegerField()  # 三杀数
    four_kill = IntegerField()  # 四杀数
    five_kill = IntegerField()  # 五杀数
    multi_kills = IntegerField()  # 多杀数
    vs1 = IntegerField()  # 1V1胜利数
    vs2 = IntegerField()  # 1V2胜利数
    vs3 = IntegerField()  # 1V3胜利数
    vs4 = IntegerField()  # 1V4胜利数
    vs5 = IntegerField()  # 1V5胜利数
    headshot_count = IntegerField()  # 爆头计数
    dmg_armor = IntegerField()  # 伤害护甲值
    dmg_health = IntegerField()  # 伤害生命值
    adpr = DoubleField()  # 平均每回合伤害
    fire_count = IntegerField()  # 射击次数
    hit_count = IntegerField()  # 命中次数
    rws = DoubleField()  # RWS值
    kast = DoubleField()  # KAST值
    rank = IntegerField()  # 当前排名
    old_rank = IntegerField()  # 之前排名
    we = DoubleField()  # WE值
    throws_count = IntegerField()  # 投掷物数量
    team_id = CharField(max_length=64, null=True)  # 队伍ID
    team_name = CharField(max_length=64, null=True)
    first_death = IntegerField()  # 首死数
    snipe_num = IntegerField()  # 狙击数
    mvp = BooleanField()  # 是否为MVP
    play_day = CharField(max_length=64, null=True)
    cup_name = CharField(max_length=128, null=True)  # 杯赛名称
    win = IntegerField()
    game_count = IntegerField()
    trade_frag_count = IntegerField(default=0)  # 补枪击杀数
    grenade_damage = IntegerField(default=0)  # 手雷伤害
    inferno_damage = IntegerField(default=0)  # 燃烧伤害
    kill_map = TextField(null=True)  # 对位击杀，JSON: victim player_id -> kills

    @classmethod
    def is_exist(cls, match_id: str, player_id: str) -> Optional[bool]:
        """获取用户最新的一条运动记录"""
        try:
            match_player = (cls.select()
                            .where(cls.match_id == match_id, cls.player_id == player_id)
                            .limit(1)
                            .get())
            return True
        except cls.DoesNotExist:
            return False
        except Exception as e:
            logger.error(f"获取最新记录失败: {str(e)}")
            return False

    @classmethod
    def get_cup_day_set(cls, cup_name=None):
        try:
            query = (cls
                     .select(cls.play_day, fn.COUNT(cls.id).alias('count'))
                     .group_by(cls.play_day)
                     .having(fn.COUNT(cls.id) > 1))
            # 自定义比赛的候选行 cup_name 为 null，必须按 cup_name 过滤，
            # 否则会污染首页「日期导航」
            if cup_name:
                query = query.where(cls.cup_name == cup_name)
            return [record.play_day for record in query]
        except Exception as e:
            logger.error(f"get_dup_day_set error: {e}")
            return []

    @classmethod
    def get_match_exploit(cls, cup_name: str, player_id, play_day: str) -> Optional[Dict[str, Any]]:
        try:
            totals = {
                'win_count': cls.win,
                'total_kills': cls.kill,
                'total_assists': cls.assist,
                'total_deaths': cls.death,
                'total_first_kills': cls.entry_kill,
                'total_first_deaths': cls.first_death,
                'total_headshots': cls.headshot,
                'total_2k': cls.two_kill,
                'total_3k': cls.three_kill,
                'total_4k': cls.four_kill,
                'total_5k': cls.five_kill,
                'total_multi_kills': cls.multi_kills,
                'total_1v1': cls.vs1,
                'total_1v2': cls.vs2,
                'total_1v3': cls.vs3,
                'total_1v4': cls.vs4,
                'total_1v5': cls.vs5,
                'total_flashes': cls.flash,
                'total_flash_success': cls.flash_success,
                'total_flash_teammate': cls.flash_teammate,
                'total_hit_count': cls.hit_count,
                'total_fire_count': cls.fire_count,
                'total_throws_count': cls.throws_count,
                'total_snipe_num': cls.snipe_num,
                'total_mvp': cls.mvp_value,
                'total_game_count': cls.game_count,
                'total_health_damage': cls.dmg_health,
                'total_kast_rounds': cls.kast,
                'total_trade_frags': cls.trade_frag_count,
                'total_grenade_damage': cls.grenade_damage,
                'total_inferno_damage': cls.inferno_damage,
            }
            averages = {
                'avg_kills': cls.kill,
                'avg_deaths': cls.death,
                'avg_assists': cls.assist,
                'avg_damage_armar': cls.dmg_armor,
                'avg_damage_health': cls.dmg_health,
                'avg_rating': cls.rating,
                'avg_pw_rating': cls.pw_rating,
                'avg_rws': cls.rws,
                'avg_we': cls.we,
                'avg_throws_count': cls.throws_count,
            }
            query = cls.select(
                fn.COUNT(fn.DISTINCT(cls.match_id)).alias('match_count'),
                fn.COALESCE(
                    fn.SUM(Case(None, [(cls.mvp == True, 1)], 0)), 0
                ).alias('match_mvp_count'),
                *(fn.COALESCE(fn.SUM(field), 0).alias(name)
                  for name, field in totals.items()),
                *(fn.COALESCE(fn.AVG(field), 0).alias(name)
                  for name, field in averages.items()),
            )

            # 应用过滤条件
            if cup_name:
                query = query.where(cls.cup_name == cup_name)
            if player_id:
                query = query.where(cls.player_id == player_id)
            if play_day:
                query = query.where(cls.play_day == play_day)

            result = query.get()
            if not result or result.match_count == 0:
                logger.info("No matching records found")
                return None

            data = {name: int(getattr(result, name, 0) or 0) for name in totals}
            data.update({name: float(getattr(result, name, 0) or 0) for name in averages})
            data['match_count'] = int(result.match_count or 0)
            data['match_mvp_count'] = int(result.match_mvp_count or 0)
            rounds = data['total_game_count']
            flashes = data['total_flash_success'] + data['total_flash_teammate']
            opening_duels = data['total_first_kills'] + data['total_first_deaths']
            multi_kill_rounds = sum(data[name] for name in ('total_2k', 'total_3k', 'total_4k', 'total_5k'))
            utility_damage = data['total_grenade_damage'] + data['total_inferno_damage']

            def ratio(numerator, denominator):
                return round(float(numerator or 0) / float(denominator or 0), 4) if denominator else 0.0

            data.update({
                'total_rounds': rounds,
                'kd_ratio': ratio(data['total_kills'], data['total_deaths']),
                'fk_fd_ratio': ratio(data['total_first_kills'], data['total_first_deaths']),
                'win_rate': ratio(data['win_count'], data['match_count']),
                'avg_adpr': ratio(data['total_health_damage'], rounds),
                'avg_kast': ratio(data['total_kast_rounds'], rounds),
                'kast_ratio': ratio(data['total_kast_rounds'], rounds),
                'avg_headshot_ratio': ratio(data['total_headshots'], data['total_kills']),
                'headshot_ratio': ratio(data['total_headshots'], data['total_kills']),
                'kills_per_round': ratio(data['total_kills'], rounds),
                'deaths_per_round': ratio(data['total_deaths'], rounds),
                'assists_per_round': ratio(data['total_assists'], rounds),
                'opening_duel_win_rate': ratio(data['total_first_kills'], opening_duels),
                'opening_duels_per_round': ratio(opening_duels, rounds),
                'throws_per_round': ratio(data['total_throws_count'], rounds),
                'multi_kill_rounds': multi_kill_rounds,
                'multi_kill_round_rate': ratio(multi_kill_rounds, rounds),
                'mvp_match_rate': ratio(data['match_mvp_count'], data['match_count']),
                'enemy_flashes_per_round': ratio(data['total_flash_success'], rounds),
                'team_flashes_per_round': ratio(data['total_flash_teammate'], rounds),
                'team_flash_share': ratio(data['total_flash_teammate'], flashes),
                'trade_kill_share': ratio(data['total_trade_frags'], data['total_kills']),
                'total_utility_damage': utility_damage,
                'utility_damage_per_round': ratio(utility_damage, rounds),
                # 上游 flash 始终为 0，无法组成成功率；保留旧字段仅为 API 兼容。
                'flash_success_ratio': 0.0,
                'flash_teammate_ratio': 0.0,
            })
            return data

        except cls.DoesNotExist:
            logger.info("No records found for the given criteria")
            return None
        except Exception as e:
            logger.error(f"get_match_exploit error: {e}")
            return None

    @classmethod
    def get_external_player_stats(cls, cup_names: List[str],
                                  player_id: str = None) -> List[Dict[str, Any]]:
        """Aggregate every player's public statistics across selected seasons."""
        cup_names = list(dict.fromkeys(name for name in (cup_names or []) if name))
        if not cup_names:
            return []

        total_fields = {
            'win_count': cls.win,
            'total_kills': cls.kill,
            'total_bot_kills': cls.bot_kill,
            'total_negative_kills': cls.neg_kill,
            'total_handgun_kills': cls.handgun_kill,
            'total_first_kills': cls.entry_kill,
            'total_awp_kills': cls.awp_kill,
            'total_deaths': cls.death,
            'total_entry_deaths': cls.entry_death,
            'total_first_deaths': cls.first_death,
            'total_assists': cls.assist,
            'total_headshots': cls.headshot,
            'total_damage': cls.damage,
            'total_item_throws': cls.item_throw,
            'total_flashes': cls.flash,
            'total_flash_teammate': cls.flash_teammate,
            'total_flash_success': cls.flash_success,
            'total_end_games': cls.end_game,
            'total_mvp': cls.mvp_value,
            'total_score': cls.score,
            'total_2k': cls.two_kill,
            'total_3k': cls.three_kill,
            'total_4k': cls.four_kill,
            'total_5k': cls.five_kill,
            'total_multi_kills': cls.multi_kills,
            'total_1v1': cls.vs1,
            'total_1v2': cls.vs2,
            'total_1v3': cls.vs3,
            'total_1v4': cls.vs4,
            'total_1v5': cls.vs5,
            'total_headshot_count': cls.headshot_count,
            'total_armor_damage': cls.dmg_armor,
            'total_health_damage': cls.dmg_health,
            'total_fire_count': cls.fire_count,
            'total_hit_count': cls.hit_count,
            'total_throws_count': cls.throws_count,
            'total_snipe_num': cls.snipe_num,
            'total_game_count': cls.game_count,
            'total_kast_rounds': cls.kast,
            'total_trade_frags': cls.trade_frag_count,
            'total_grenade_damage': cls.grenade_damage,
            'total_inferno_damage': cls.inferno_damage,
        }
        average_fields = {
            'avg_kills': cls.kill,
            'avg_deaths': cls.death,
            'avg_assists': cls.assist,
            'avg_rating': cls.rating,
            'avg_pw_rating': cls.pw_rating,
            'avg_rws': cls.rws,
            'avg_we': cls.we,
            'avg_armor_damage': cls.dmg_armor,
            'avg_health_damage': cls.dmg_health,
            'avg_throws_count': cls.throws_count,
        }
        select_fields = [
            cls.player_id,
            fn.MAX(cls.nickname).alias('nickname'),
            fn.MAX(cls.avatar).alias('avatar'),
            fn.COUNT(fn.DISTINCT(cls.match_id)).alias('match_count'),
            fn.COALESCE(
                fn.SUM(Case(None, [(cls.mvp == True, 1)], 0)), 0
            ).alias('match_mvp_count'),
        ]
        select_fields.extend(
            fn.COALESCE(fn.SUM(field), 0).alias(name)
            for name, field in total_fields.items()
        )
        select_fields.extend(
            fn.COALESCE(fn.AVG(field), 0).alias(name)
            for name, field in average_fields.items()
        )

        conditions = [cls.cup_name.in_(cup_names)]
        if player_id:
            conditions.append(cls.player_id == player_id)
        rows = list(
            cls.select(*select_fields)
            .where(*conditions)
            .group_by(cls.player_id)
            .dicts()
        )
        player_ids = [row['player_id'] for row in rows]
        player_map = {
            player.player_id: player
            for player in Player.select().where(Player.player_id.in_(player_ids))
        } if player_ids else {}
        matchup_map = cls._aggregate_kill_matchups(cup_names, player_ids)

        def _ratio(numerator, denominator, precision=4):
            return round(float(numerator or 0) / float(denominator or 0), precision) \
                if denominator else 0.0

        result = []
        for row in rows:
            for name in total_fields:
                row[name] = int(row.get(name) or 0)
            for name in average_fields:
                row[name] = float(row.get(name) or 0)
            row['match_count'] = int(row.get('match_count') or 0)
            row['match_mvp_count'] = int(row.get('match_mvp_count') or 0)
            rounds = row['total_game_count']
            opening_duels = row['total_first_kills'] + row['total_first_deaths']
            flash_events = row['total_flash_success'] + row['total_flash_teammate']
            multi_kill_rounds = sum(row[name] for name in ('total_2k', 'total_3k', 'total_4k', 'total_5k'))
            utility_damage = row['total_grenade_damage'] + row['total_inferno_damage']
            row['kd_ratio'] = _ratio(row['total_kills'], row['total_deaths'])
            row['fk_fd_ratio'] = _ratio(row['total_first_kills'], row['total_first_deaths'])
            row['win_rate'] = _ratio(row['win_count'], row['match_count'])
            row['headshot_ratio'] = _ratio(row['total_headshots'], row['total_kills'])
            row['avg_headshot_ratio'] = row['headshot_ratio']
            row['total_rounds'] = rounds
            row['avg_adpr'] = _ratio(row['total_health_damage'], rounds)
            row['avg_kast'] = _ratio(row['total_kast_rounds'], rounds)
            row['kast_ratio'] = row['avg_kast']
            row['kills_per_round'] = _ratio(row['total_kills'], rounds)
            row['deaths_per_round'] = _ratio(row['total_deaths'], rounds)
            row['assists_per_round'] = _ratio(row['total_assists'], rounds)
            row['opening_duel_win_rate'] = _ratio(row['total_first_kills'], opening_duels)
            row['opening_duels_per_round'] = _ratio(opening_duels, rounds)
            row['throws_per_round'] = _ratio(row['total_throws_count'], rounds)
            row['multi_kill_rounds'] = multi_kill_rounds
            row['multi_kill_round_rate'] = _ratio(multi_kill_rounds, rounds)
            row['mvp_match_rate'] = _ratio(row['match_mvp_count'], row['match_count'])
            row['enemy_flashes_per_round'] = _ratio(row['total_flash_success'], rounds)
            row['team_flashes_per_round'] = _ratio(row['total_flash_teammate'], rounds)
            row['team_flash_share'] = _ratio(row['total_flash_teammate'], flash_events)
            row['trade_kill_share'] = _ratio(row['total_trade_frags'], row['total_kills'])
            row['total_utility_damage'] = utility_damage
            row['utility_damage_per_round'] = _ratio(utility_damage, rounds)
            row['kill_matchups'] = matchup_map.get(row['player_id'], [])
            # WMPVP 当前不返回闪光弹投掷数，旧比率没有可靠分母。
            row['flash_success_ratio'] = 0.0
            row['flash_teammate_ratio'] = 0.0
            row['hit_ratio'] = _ratio(row['total_hit_count'], row['total_fire_count'])

            player = player_map.get(row['player_id'])
            if player:
                row.update({
                    'nickname': player.nickname or row.get('nickname'),
                    'avatar': player.avatar or row.get('avatar'),
                    'alias_name': player.alias_name or '',
                    'steam_id': player.steam_id or '',
                    'live_url': player.live_url or '',
                    'live_room_id': Player.live_room_id(player.live_url),
                    'in_library': bool(player.in_library),
                })
            else:
                row.update({
                    'alias_name': '',
                    'steam_id': '',
                    'live_url': '',
                    'live_room_id': '',
                    'in_library': False,
                })
            result.append(row)

        result.sort(key=lambda item: (-item['avg_rating'], item['player_id']))
        return result

    @classmethod
    def _aggregate_kill_matchups(cls, cup_names: List[str],
                                 player_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        """Aggregate WMPVP killMap JSON without requiring demo parsing."""
        if not cup_names or not player_ids:
            return {}
        counters = {player_id: Counter() for player_id in player_ids}
        rows = (cls.select(cls.player_id, cls.kill_map)
                .where(cls.cup_name.in_(cup_names), cls.player_id.in_(player_ids)))
        for row in rows:
            try:
                values = json.loads(row.kill_map or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(values, dict):
                continue
            for victim_id, kills in values.items():
                try:
                    count = int(kills or 0)
                except (TypeError, ValueError):
                    continue
                if count > 0:
                    counters[row.player_id][str(victim_id)] += count

        victim_ids = {victim_id for counter in counters.values() for victim_id in counter}
        victims = {
            player.player_id: player
            for player in Player.select().where(Player.player_id.in_(victim_ids))
        } if victim_ids else {}
        return {
            player_id: [
                {
                    'player_id': victim_id,
                    'nickname': ((victims.get(victim_id).alias_name or victims.get(victim_id).nickname)
                                 if victims.get(victim_id) else victim_id),
                    'kills': kills,
                }
                for victim_id, kills in counter.most_common()
            ]
            for player_id, counter in counters.items()
        }

    @classmethod
    def get_player_kill_matchups(cls, cup_name: str, player_id: str,
                                 play_day: str = None) -> List[Dict[str, Any]]:
        if not cup_name or not player_id:
            return []
        if not play_day:
            return cls._aggregate_kill_matchups([cup_name], [player_id]).get(player_id, [])
        counter = Counter()
        rows = (cls.select(cls.kill_map)
                .where(cls.cup_name == cup_name,
                       cls.player_id == player_id,
                       cls.play_day == play_day))
        for row in rows:
            try:
                values = json.loads(row.kill_map or '{}')
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(values, dict):
                for victim_id, kills in values.items():
                    try:
                        count = int(kills or 0)
                    except (TypeError, ValueError):
                        continue
                    if count > 0:
                        counter[str(victim_id)] += count
        victim_ids = list(counter)
        victims = {
            player.player_id: player
            for player in Player.select().where(Player.player_id.in_(victim_ids))
        } if victim_ids else {}
        return [
            {
                'player_id': victim_id,
                'nickname': ((victims[victim_id].alias_name or victims[victim_id].nickname)
                             if victim_id in victims else victim_id),
                'kills': kills,
            }
            for victim_id, kills in counter.most_common()
        ]

    @classmethod
    def get_player_map_stats(cls, cup_name: str, player_id: str, play_day: str = None) -> List[Dict[str, Any]]:
        """获取选手地图统计数据"""
        try:
            # 构建查询条件
            conditions = [
                cls.player_id == player_id,
                Match.cup_name == cup_name
            ]
            
            if play_day:
                conditions.append(cls.play_day == play_day)
            
            # 联表查询获取地图信息
            query = (cls.select(
                Match.map_name_en.alias('map_name_en'),
                fn.MAX(Match.map_name).alias('map_name'),
                fn.MAX(Match.map_url).alias('map_url'),
                fn.MAX(Match.map_logo).alias('map_logo'),
                fn.COUNT(fn.DISTINCT(cls.match_id)).alias('match_count'),
                fn.COALESCE(fn.SUM(cls.win), 0).alias('win_count'),
                fn.COALESCE(fn.SUM(cls.kill), 0).alias('total_kills'),
                fn.COALESCE(fn.SUM(cls.death), 0).alias('total_deaths'),
                fn.COALESCE(fn.SUM(cls.assist), 0).alias('total_assists'),
                fn.COALESCE(fn.SUM(cls.headshot), 0).alias('total_headshots'),
                fn.COALESCE(fn.SUM(cls.dmg_health), 0).alias('total_health_damage'),
                fn.COALESCE(fn.SUM(cls.kast), 0).alias('total_kast_rounds'),
                fn.COALESCE(fn.SUM(cls.game_count), 0).alias('total_rounds'),
                fn.COALESCE(fn.AVG(cls.pw_rating), 0).alias('avg_rating'),
                fn.COALESCE(fn.AVG(cls.kill), 0).alias('avg_kills'),
                fn.COALESCE(fn.AVG(cls.death), 0).alias('avg_deaths'),
                fn.COALESCE(fn.AVG(cls.assist), 0).alias('avg_assists'),
                fn.COALESCE(fn.SUM(cls.mvp_value), 0).alias('total_mvp'),
                fn.COALESCE(fn.SUM(cls.two_kill), 0).alias('total_2k'),
                fn.COALESCE(fn.SUM(cls.three_kill), 0).alias('total_3k'),
                fn.COALESCE(fn.SUM(cls.four_kill), 0).alias('total_4k'),
                fn.COALESCE(fn.SUM(cls.five_kill), 0).alias('total_5k'),
                fn.COALESCE(fn.SUM(cls.vs1), 0).alias('total_1v1'),
                fn.COALESCE(fn.SUM(cls.vs2), 0).alias('total_1v2'),
                fn.COALESCE(fn.SUM(cls.vs3), 0).alias('total_1v3'),
                fn.COALESCE(fn.SUM(cls.vs4), 0).alias('total_1v4'),
                fn.COALESCE(fn.SUM(cls.vs5), 0).alias('total_1v5'),
            )
            .join(Match, on=(cls.match_id == Match.match_id))
            .where(*conditions)
            .group_by(Match.map_name_en)
            .order_by(fn.COUNT(fn.DISTINCT(cls.match_id)).desc()))
            
            results = query.execute()
            map_stats = []
            
            for result in results:
                win_rate = (result.win_count / result.match_count * 100) if result.match_count > 0 else 0
                kd_ratio = (result.total_kills / result.total_deaths) if result.total_deaths > 0 else 0
                headshot_ratio = (result.total_headshots / result.total_kills) if result.total_kills > 0 else 0
                avg_adpr = (result.total_health_damage / result.total_rounds) if result.total_rounds > 0 else 0
                kast_ratio = (result.total_kast_rounds / result.total_rounds) if result.total_rounds > 0 else 0
                
                map_stats.append({
                    'map_name': result.map_name,
                    'map_name_en': result.match.map_name_en,
                    'map_url': result.map_url,
                    'map_logo': result.map_logo,
                    'match_count': result.match_count,
                    'win_count': result.win_count,
                    'win_rate': win_rate,
                    'total_kills': result.total_kills,
                    'total_deaths': result.total_deaths,
                    'total_assists': result.total_assists,
                    'avg_rating': float(result.avg_rating or 0),
                    'avg_kills': float(result.avg_kills or 0),
                    'avg_deaths': float(result.avg_deaths or 0),
                    'avg_assists': float(result.avg_assists or 0),
                    'avg_headshot_ratio': float(headshot_ratio),
                    'avg_adpr': float(avg_adpr),
                    'avg_kast': float(kast_ratio),
                    'kast_ratio': float(kast_ratio),
                    'total_rounds': int(result.total_rounds or 0),
                    'kd_ratio': kd_ratio,
                    'total_mvp': result.total_mvp or 0,
                    'total_2k': result.total_2k or 0,
                    'total_3k': result.total_3k or 0,
                    'total_4k': result.total_4k or 0,
                    'total_5k': result.total_5k or 0,
                    'total_1v1': result.total_1v1 or 0,
                    'total_1v2': result.total_1v2 or 0,
                    'total_1v3': result.total_1v3 or 0,
                    'total_1v4': result.total_1v4 or 0,
                    'total_1v5': result.total_1v5 or 0,
                })
            
            return map_stats
            
        except Exception as e:
            logger.error(f"获取选手地图统计数据失败: {str(e)}")
            return []

    @classmethod
    def get_player_match_records(cls, cup_name: str, player_id: str,
                                 play_day: str = None) -> List[Dict[str, Any]]:
        """获取选手在指定赛季（或比赛日）的逐场比赛记录。"""
        try:
            conditions = [
                cls.player_id == player_id,
                cls.cup_name == cup_name,
                Match.cup_name == cup_name,
            ]
            if play_day:
                conditions.append(cls.play_day == play_day)

            records = list(
                cls.select(
                    cls.match_id,
                    cls.play_day,
                    cls.team.alias('player_team'),
                    cls.team_name.alias('player_team_name'),
                    cls.win,
                    cls.kill,
                    cls.death,
                    cls.assist,
                    cls.entry_kill,
                    cls.first_death,
                    cls.adpr,
                    cls.rating,
                    cls.pw_rating,
                    cls.kast,
                    cls.game_count.alias('round_count'),
                    cls.headshot_ratio,
                    cls.mvp,
                    Match.start_time,
                    Match.end_time,
                    Match.duration,
                    Match.map_name,
                    Match.map_name_en,
                    Match.map_url,
                    Match.game_mode,
                    Match.team1_name,
                    Match.team1_score,
                    Match.team2_name,
                    Match.team2_score,
                    Match.win_team,
                )
                .join(Match, on=(cls.match_id == Match.match_id))
                .where(*conditions)
                .order_by(Match.start_time.desc(), cls.match_id.desc())
                .dicts()
            )
            for record in records:
                rounds = int(record.get('round_count') or 0)
                record['kast_ratio'] = round(float(record.get('kast') or 0) / rounds, 4) if rounds else 0.0
            return records
        except Exception as e:
            logger.error(f"获取选手逐场比赛记录失败: {str(e)}")
            return []

    class Meta:
        table_name = 'match_player'

        ## 联合主键
        indexes = (
            (('match_id', 'player_id'), True),
        )


class Season(BaseModel, CRUDMixin):
    """赛季定义模型：兼容官方 cupName 赛季（official）与自定义名单赛季（custom）"""
    cup_name = CharField(max_length=128, unique=True)  # URL / 内部标识，宜用英文 slug
    cup_alias = CharField(max_length=128, null=True)  # 页面展示名
    name = CharField(max_length=128, null=True)  # 兼容旧字段，等同展示名
    match_type = CharField(max_length=32, default='custom')  # 'official' | 'custom'
    start_date = DateTimeField()  # 赛季统计起点，精确到秒
    end_date = DateTimeField()  # 赛季统计终点，精确到秒
    status = CharField(max_length=16, default='active')  # 'active' | 'archived'
    hit_ratio = FloatField(default=0.6)  # 场内库内人数占比门槛，默认 60%
    champion_enabled = BooleanField(default=False)  # 是否计算每日冠军/亚军；自定义赛季默认关闭

    class Meta:
        table_name = 'season'

    @classmethod
    def get_by_cup(cls, cup_name: str) -> Optional[Dict[str, Any]]:
        """根据 cup_name 获取赛季"""
        try:
            record = cls.get(cls.cup_name == cup_name)
            return record.to_dict()
        except cls.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"获取赛季失败: {str(e)}")
            return None

    @classmethod
    def get_active_by_type(cls, match_type: str) -> List[Dict[str, Any]]:
        """获取指定类型的 active 赛季列表"""
        try:
            query = cls.select().where(cls.match_type == match_type, cls.status == 'active')
            return list(query.dicts())
        except Exception as e:
            logger.error(f"获取赛季列表失败: {str(e)}")
            return []

    @classmethod
    def get_active(cls) -> List[Dict[str, Any]]:
        """获取全部 active 赛季"""
        try:
            query = cls.select().where(cls.status == 'active')
            return list(query.dicts())
        except Exception as e:
            logger.error(f"获取赛季列表失败: {str(e)}")
            return []

    @classmethod
    def display_name(cls, cup_name: str) -> str:
        rec = cls.get_by_cup(cup_name) if cup_name else None
        if not rec:
            return cup_name or ''
        return rec.get('cup_alias') or rec.get('name') or rec.get('cup_name') or cup_name

    @classmethod
    def annotate(cls, rec: Dict[str, Any]) -> Dict[str, Any]:
        if not rec:
            return rec
        rec['display_name'] = rec.get('cup_alias') or rec.get('name') or rec.get('cup_name')
        return rec

    @classmethod
    def delete_with_related_data(cls, cup_name: str) -> Optional[Dict[str, int]]:
        """Delete a season and its derived data while retaining raw match rows.

        Match and MatchPlayer are the reusable raw crawl result.  They are
        detached from the deleted season so recreating the same cup does not
        accidentally expose stale statistics.
        """
        season = cls.get_or_none(cls.cup_name == cup_name)
        if season is None:
            return None

        with db.atomic():
            counts = {
                'rosters': SeasonRoster.delete().where(
                    SeasonRoster.season_cup_name == cup_name
                ).execute(),
                'selections': MatchSelection.delete().where(
                    MatchSelection.season_cup_name == cup_name
                ).execute(),
                'titles': PlayerTitle.delete().where(
                    PlayerTitle.cup_name == cup_name
                ).execute(),
                'champions': CupDayChampion.delete().where(
                    CupDayChampion.cup_name == cup_name
                ).execute(),
                'match_players_detached': MatchPlayer.update(cup_name=None).where(
                    MatchPlayer.cup_name == cup_name
                ).execute(),
                'matches_detached': Match.update(cup_name=None).where(
                    Match.cup_name == cup_name
                ).execute(),
                'crawl_configs': Config.delete().where(Config.key.in_([
                    f'crawl_enabled:{cup_name}',
                    f'crawl_status:{cup_name}',
                ])).execute(),
            }
            counts['seasons'] = cls.delete().where(cls.cup_name == cup_name).execute()
        return counts


class SeasonRoster(BaseModel, CRUDMixin):
    """赛季名单（白名单 player_id）"""
    season_cup_name = CharField(max_length=128)  # 关联 Season.cup_name
    player_id = CharField(max_length=64)  # 玩家ID

    class Meta:
        table_name = 'season_roster'
        indexes = (
            (('season_cup_name', 'player_id'), True),
        )

    @classmethod
    def get_player_ids(cls, season_cup_name: str) -> List[str]:
        """获取某赛季名单 player_id 列表"""
        try:
            query = cls.select(cls.player_id).where(cls.season_cup_name == season_cup_name)
            return [r.player_id for r in query]
        except Exception as e:
            logger.error(f"获取名单失败: {str(e)}")
            return []

    @classmethod
    def set_roster(cls, season_cup_name: str, player_ids: List[str]) -> None:
        """整体替换某赛季名单"""
        try:
            with db.atomic():
                cls.delete().where(cls.season_cup_name == season_cup_name).execute()
                seen = set()
                for pid in player_ids or []:
                    pid = (pid or '').strip()
                    if pid and pid not in seen:
                        seen.add(pid)
                        cls.create(season_cup_name=season_cup_name, player_id=pid)
                        Player.ensure_library_player(pid)
        except Exception as e:
            logger.error(f"设置名单失败: {str(e)}")
            raise


class MatchSelection(BaseModel, CRUDMixin):
    """赛季比赛纳入/剔除状态。approved 算入统计，rejected 剔除。"""
    match_id = CharField(max_length=64)
    season_cup_name = CharField(max_length=128)  # 关联 Season.cup_name
    status = CharField(max_length=16, default='approved')  # 'approved' | 'rejected'（旧 pending 迁移为 approved）
    source_type = CharField(max_length=16, default='custom')  # 'custom' | 'official'
    play_day = CharField(max_length=8, null=True)  # 冗余，便于按天查询
    roster_hit_count = IntegerField(default=0)  # 库内命中人数
    note = TextField(null=True)

    class Meta:
        table_name = 'match_selection'
        indexes = (
            (('match_id', 'season_cup_name'), True),
        )

    @classmethod
    def get_by_match(cls, match_id: str, season_cup_name: str) -> Optional[Dict[str, Any]]:
        """根据 match_id + 赛季获取确认记录"""
        try:
            record = (cls.select()
                      .where(cls.match_id == match_id, cls.season_cup_name == season_cup_name)
                      .get())
            return record.to_dict()
        except cls.DoesNotExist:
            return None
        except Exception as e:
            logger.error(f"获取确认记录失败: {str(e)}")
            return None

    @classmethod
    def is_rejected(cls, match_id: str, season_cup_name: str) -> bool:
        sel = cls.get_by_match(match_id, season_cup_name)
        return bool(sel and sel.get('status') == 'rejected')

    @classmethod
    def list_by_season(cls, season_cup_name: str, status: str = None,
                       play_day: str = None) -> List[Dict[str, Any]]:
        try:
            query = cls.select().where(cls.season_cup_name == season_cup_name)
            if status:
                query = query.where(cls.status == status)
            if play_day:
                query = query.where(cls.play_day == play_day)
            query = query.order_by(cls.play_day.desc(), cls.roster_hit_count.desc())
            return list(query.dicts())
        except Exception as e:
            logger.error(f"列出赛季比赛失败: {str(e)}")
            return []

    @classmethod
    def upsert_included(cls, match_id: str, season_cup_name: str, play_day: str,
                        roster_hit_count: int, source_type: str = 'custom') -> bool:
        """采集命中后纳入。已剔除的保持 rejected，返回 False 表示不要写 cup_name。"""
        try:
            existing = cls.get_or_none((cls.match_id == match_id) & (cls.season_cup_name == season_cup_name))
            if existing is None:
                cls.create(
                    match_id=match_id,
                    season_cup_name=season_cup_name,
                    status='approved',
                    source_type=source_type,
                    play_day=play_day,
                    roster_hit_count=roster_hit_count,
                )
                return True
            if existing.status == 'rejected':
                update_dict = {
                    'roster_hit_count': max(existing.roster_hit_count or 0, roster_hit_count),
                }
                if play_day:
                    update_dict['play_day'] = play_day
                cls.update(**update_dict).where(cls.id == existing.id).execute()
                return False
            update_dict = {
                'roster_hit_count': max(existing.roster_hit_count or 0, roster_hit_count),
                'status': 'approved',
                'source_type': source_type or existing.source_type,
            }
            if play_day:
                update_dict['play_day'] = play_day
            cls.update(**update_dict).where(cls.id == existing.id).execute()
            return True
        except Exception as e:
            logger.error(f"更新纳入记录失败: {str(e)}")
            return False

    @classmethod
    def upsert_pending(cls, match_id: str, season_cup_name: str, play_day: str, roster_hit_count: int) -> None:
        """兼容旧调用：等同纳入（不再走 pending）。"""
        cls.upsert_included(match_id, season_cup_name, play_day, roster_hit_count, source_type='custom')

    @classmethod
    def set_status(cls, match_id: str, season_cup_name: str, status: str) -> bool:
        existing = cls.get_or_none((cls.match_id == match_id) & (cls.season_cup_name == season_cup_name))
        if existing is None:
            return False
        existing.status = status
        existing.save()
        return True


class AdminUser(BaseModel, CRUDMixin):
    """后台管理员"""
    username = CharField(max_length=64, unique=True)
    password_hash = CharField(max_length=255)
    last_login_at = DateTimeField(null=True)

    class Meta:
        table_name = 'admin_user'


class SchemaMigration(BaseModel):
    version = CharField(max_length=64, unique=True)
    applied_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = 'schema_migrations'


def _column_exists(table_name: str, column_name: str) -> bool:
    if is_postgres():
        cursor = db.execute_sql(
            "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (table_name, column_name),
        )
        return cursor.fetchone() is not None
    cursor = db.execute_sql(f"PRAGMA table_info('{table_name}')")
    return any(row[1] == column_name for row in cursor.fetchall())


def _table_exists(table_name: str) -> bool:
    if is_postgres():
        cursor = db.execute_sql(
            "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s",
            (table_name,),
        )
        return cursor.fetchone() is not None
    cursor = db.execute_sql(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def _add_column(table_name: str, column_name: str, ddl: str) -> None:
    db.execute_sql(f'ALTER TABLE {table_name} ADD COLUMN {column_name} {ddl}')


def migrate_schema():
    """版本化迁移：启动时自动补齐未应用的变更。"""
    from migrations import run_migrations
    run_migrations()


HISTORY_IMPORT_VERSION = 'data_001_cs_history'
HISTORY_IMPORT_TABLES = (
    'config', 'match', 'match_player', 'player', 'cup_day_champion',
    'player_title', 'season', 'match_selection',
)


def import_history_sql(sql_path: str = None) -> Dict[str, Any]:
    """Import the legacy data seed into a fresh PostgreSQL database once."""
    if not is_postgres():
        logger.info('历史 SQL 仅用于 PostgreSQL 部署，SQLite 环境跳过导入')
        return {'status': 'skipped_sqlite'}

    if SchemaMigration.select().where(
        SchemaMigration.version == HISTORY_IMPORT_VERSION
    ).exists():
        logger.info('历史 SQL 已导入，跳过')
        return {'status': 'already_imported'}

    existing_counts = {}
    for table_name in HISTORY_IMPORT_TABLES:
        cursor = db.execute_sql(f'SELECT COUNT(*) FROM "{table_name}"')
        existing_counts[table_name] = cursor.fetchone()[0]
    nonempty = {table: count for table, count in existing_counts.items() if count}
    if nonempty:
        logger.warning(f'目标库已有业务数据，为避免覆盖已跳过历史 SQL 导入: {nonempty}')
        return {'status': 'skipped_nonempty', 'counts': nonempty}

    source_path = sql_path or HISTORY_SQL_PATH
    try:
        with open(source_path, 'r', encoding='utf-8') as sql_file:
            sql = sql_file.read()
    except OSError as exc:
        raise RuntimeError(f'无法读取历史 SQL: {source_path}') from exc
    if not sql.strip():
        raise RuntimeError(f'历史 SQL 为空: {source_path}')

    with db.atomic():
        # The dump contains literal percent signs. Execute without an empty params
        # tuple so psycopg2 does not interpret them as placeholder syntax.
        cursor = db.connection().cursor()
        try:
            cursor.execute(sql)
        finally:
            cursor.close()
        # 全新部署会先建好最新表结构再导入历史数据，此时 007 迁移已经标记完成；
        # 根据已导入的冠军记录补回历史赛季的开关状态。
        if _column_exists('season', 'champion_enabled'):
            enabled = 'TRUE' if is_postgres() else '1'
            db.execute_sql(
                f'UPDATE season SET champion_enabled = {enabled} '
                'WHERE EXISTS (SELECT 1 FROM cup_day_champion c WHERE c.cup_name = season.cup_name)'
            )
        if _column_exists('player', 'wanmei_avatar'):
            db.execute_sql(
                "UPDATE player SET wanmei_avatar = avatar, avatar_source = 'wanmei' "
                "WHERE avatar IS NOT NULL AND wanmei_avatar IS NULL"
            )
        imported = SchemaMigration.select().where(
            SchemaMigration.version == HISTORY_IMPORT_VERSION
        ).exists()
        if not imported:
            raise RuntimeError(f'历史 SQL 缺少导入标记: {HISTORY_IMPORT_VERSION}')

    imported_counts = {}
    for table_name in HISTORY_IMPORT_TABLES:
        cursor = db.execute_sql(f'SELECT COUNT(*) FROM "{table_name}"')
        imported_counts[table_name] = cursor.fetchone()[0]
    logger.info(f'历史 SQL 导入完成: {imported_counts}')
    return {'status': 'imported', 'counts': imported_counts}


def create_tables():
    """Create database tables if they don't exist, then apply migrations."""
    with db:
        db.create_tables([Config, Match, MatchPlayer, Player, CupDayChampion, PlayerTitle,
                          Season, SeasonRoster, MatchSelection, AdminUser, SchemaMigration], safe=True)
    migrate_schema()
