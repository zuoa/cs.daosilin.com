from datetime import datetime
from typing import List, Dict, Any, Optional

from peewee import *

from ajlog import logger
from config import DB_PATH


class DatabaseConfig:
    """数据库配置类"""

    def __init__(self, db_path: str = 'app.db'):
        self.db_path = db_path
        self.database = SqliteDatabase(db_path)

    def get_database(self):
        return self.database


# 全局数据库实例
db_config = DatabaseConfig(DB_PATH)
db = db_config.get_database()


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
    alias_name = CharField(max_length=255, null=True)  # 别名，多个别名用逗号分隔
    steam_id = CharField(max_length=64, null=True)  # Steam ID

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
    def get_cup_day_set(cls):
        try:
            query = (cls
                     .select(cls.play_day, fn.COUNT(cls.id).alias('count'))
                     .group_by(cls.play_day)
                     .having(fn.COUNT(cls.id) > 1))
            return [record.play_day for record in query]
        except Exception as e:
            logger.error(f"get_dup_day_set error: {e}")
            return []

    @classmethod
    def get_match_exploit(cls, cup_name: str, player_id, play_day: str) -> Optional[Dict[str, Any]]:
        try:
            # 使用 COALESCE 处理 NULL 值，避免除零错误
            query = cls.select(
                fn.COUNT(fn.DISTINCT(cls.match_id)).alias('match_count'),
                fn.COALESCE(fn.SUM(cls.win), 0).alias('win_count'),
                fn.COALESCE(fn.SUM(cls.kill), 0).alias('total_kills'),
                fn.COALESCE(fn.SUM(cls.assist), 0).alias('total_assists'),
                fn.COALESCE(fn.SUM(cls.death), 0).alias('total_deaths'),
                fn.COALESCE(fn.SUM(cls.entry_kill), 0).alias('total_first_kills'),
                fn.COALESCE(fn.SUM(cls.first_death), 0).alias('total_first_deaths'),
                fn.COALESCE(fn.SUM(cls.headshot), 0).alias('total_headshots'),
                fn.COALESCE(fn.SUM(cls.two_kill), 0).alias('total_2k'),
                fn.COALESCE(fn.SUM(cls.three_kill), 0).alias('total_3k'),
                fn.COALESCE(fn.SUM(cls.four_kill), 0).alias('total_4k'),
                fn.COALESCE(fn.SUM(cls.five_kill), 0).alias('total_5k'),
                fn.COALESCE(fn.SUM(cls.multi_kills), 0).alias('total_multi_kills'),
                fn.COALESCE(fn.SUM(cls.vs2), 0).alias('total_1v2'),
                fn.COALESCE(fn.SUM(cls.vs3), 0).alias('total_1v3'),
                fn.COALESCE(fn.SUM(cls.vs4), 0).alias('total_1v4'),
                fn.COALESCE(fn.SUM(cls.vs5), 0).alias('total_1v5'),
                fn.COALESCE(fn.SUM(cls.flash), 0).alias('total_flashes'),
                fn.COALESCE(fn.SUM(cls.flash_success), 0).alias('total_flash_success'),
                fn.COALESCE(fn.SUM(cls.flash_teammate), 0).alias('total_flash_teammate'),
                fn.COALESCE(fn.SUM(cls.hit_count), 0).alias('total_hit_count'),
                fn.COALESCE(fn.SUM(cls.throws_count), 0).alias('total_throws_count'),
                fn.COALESCE(fn.SUM(cls.snipe_num), 0).alias('total_snipe_num'),
                fn.COALESCE(fn.SUM(cls.fire_count), 0).alias('total_fire_count'),

                # 安全的除法运算，避免除零错误
                Case(None, [
                    (fn.SUM(cls.death) > 0, fn.ROUND(fn.SUM(cls.kill) * 1.0 / fn.SUM(cls.death), 2))
                ], 0).alias('kd_ratio'),

                Case(None, [
                    (fn.SUM(cls.first_death) > 0, fn.ROUND(fn.SUM(cls.entry_kill) * 1.0 / fn.SUM(cls.first_death), 2))
                ], 0).alias('fk_fd_ratio'),

                Case(None, [
                    (fn.SUM(cls.flash) > 0, fn.ROUND(fn.SUM(cls.flash_success) * 1.0 / fn.SUM(cls.flash), 2))
                ], 0).alias('flash_success_ratio'),

                # 计算胜率
                Case(None, [
                    (fn.COUNT(fn.DISTINCT(cls.match_id)) > 0, fn.ROUND(fn.COALESCE(fn.SUM(cls.win), 0) * 1.0 / fn.COUNT(fn.DISTINCT(cls.match_id)), 3))
                ], 0).alias('win_rate'),

                fn.COALESCE(fn.AVG(cls.kill), 0).alias('avg_kills'),
                fn.COALESCE(fn.AVG(cls.death), 0).alias('avg_deaths'),
                fn.COALESCE(fn.AVG(cls.assist), 0).alias('avg_assists'),
                fn.COALESCE(fn.AVG(cls.dmg_armor), 0).alias('avg_damage_armar'),
                fn.COALESCE(fn.AVG(cls.dmg_health), 0).alias('avg_damage_health'),
                fn.COALESCE(fn.AVG(cls.rating), 0).alias('avg_rating'),
                fn.COALESCE(fn.AVG(cls.pw_rating), 0).alias('avg_pw_rating'),
                fn.COALESCE(fn.AVG(cls.rws), 0).alias('avg_rws'),
                fn.COALESCE(fn.AVG(cls.we), 0).alias('avg_we'),
                fn.COALESCE(fn.AVG(cls.adpr), 0).alias('avg_adpr'),
                fn.COALESCE(fn.AVG(cls.kast), 0).alias('avg_kast'),
                fn.COALESCE(fn.AVG(cls.headshot_ratio), 0).alias('avg_headshot_ratio'),
                fn.COALESCE(fn.SUM(cls.mvp_value), 0).alias('total_mvp'),
                fn.COALESCE(fn.SUM(Case(None, [(cls.mvp == True, 1)], 0)), 0).alias('match_mvp_count'),
            )

            # 应用过滤条件
            if cup_name:
                query = query.where(cls.cup_name == cup_name)
            if player_id:
                query = query.where(cls.player_id == player_id)
            if play_day:
                query = query.where(cls.play_day == play_day)

            # 执行查询
            result = query.get()

            # 检查是否有匹配的记录
            if not result or result.match_count == 0:
                logger.info("No matching records found")
                return None

            # 手动构建返回字典，确保所有字段都有值
            return {
                'match_count': result.match_count or 0,
                'win_count': result.win_count or 0,
                'total_kills': result.total_kills or 0,
                'total_assists': result.total_assists or 0,
                'total_deaths': result.total_deaths or 0,
                'total_first_kills': result.total_first_kills or 0,
                'total_first_deaths': result.total_first_deaths or 0,
                'total_headshots': result.total_headshots or 0,
                'total_2k': result.total_2k or 0,
                'total_3k': result.total_3k or 0,
                'total_4k': result.total_4k or 0,
                'total_5k': result.total_5k or 0,
                'total_multi_kills': result.total_multi_kills or 0,
                'total_1v2': result.total_1v2 or 0,
                'total_1v3': result.total_1v3 or 0,
                'total_1v4': result.total_1v4 or 0,
                'total_1v5': result.total_1v5 or 0,
                'total_flashes': result.total_flashes or 0,
                'total_flash_success': result.total_flash_success or 0,
                'total_flash_teammate': result.total_flash_teammate or 0,
                'total_hit_count': result.total_hit_count or 0,
                'total_throws_count': result.total_throws_count or 0,
                'total_snipe_num': result.total_snipe_num or 0,
                'kd_ratio': float(result.kd_ratio or 0),
                'fk_fd_ratio': float(result.fk_fd_ratio or 0),
                'flash_success_ratio': float(result.flash_success_ratio or 0),
                'win_rate': float(result.win_rate or 0),
                'avg_kills': float(result.avg_kills or 0),
                'avg_deaths': float(result.avg_deaths or 0),
                'avg_assists': float(result.avg_assists or 0),
                'avg_damage_armar': float(result.avg_damage_armar or 0),
                'avg_damage_health': float(result.avg_damage_health or 0),
                'avg_rating': float(result.avg_rating or 0),
                'avg_pw_rating': float(result.avg_pw_rating or 0),
                'avg_rws': float(result.avg_rws or 0),
                'avg_we': float(result.avg_we or 0),
                'avg_adpr': float(result.avg_adpr or 0),
                'avg_kast': float(result.avg_kast or 0),
                'avg_headshot_ratio': float(result.avg_headshot_ratio or 0),
                'total_mvp': result.total_mvp or 0,
                'match_mvp_count': result.match_mvp_count or 0,
                'total_fire_count': result.total_fire_count or 0,
            }

        except cls.DoesNotExist:
            logger.info("No records found for the given criteria")
            return None
        except Exception as e:
            logger.error(f"get_match_exploit error: {e}")
            return None

    class Meta:
        table_name = 'match_player'

        ## 联合主键
        indexes = (
            (('match_id', 'player_id'), True),
        )


def create_tables():
    """Create database tables if they don't exist"""
    with db:
        db.create_tables([Config, Match, MatchPlayer, Player, CupDayChampion, PlayerTitle], safe=True)
