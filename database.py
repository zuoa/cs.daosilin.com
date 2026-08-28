from datetime import datetime
from typing import List, Dict, Any, Optional

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
    live_url = CharField(max_length=500, null=True)  # 直播间 URL
    in_library = BooleanField(default=False)  # 是否计入玩家库（占比门槛只认库内）

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

                Case(None, [
                    (fn.SUM(cls.flash) > 0, fn.ROUND(fn.SUM(cls.flash_teammate) * 1.0 / fn.SUM(cls.flash), 2))
                ], 0).alias('flash_teammate_ratio'),

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
                fn.COALESCE(fn.AVG(cls.throws_count), 0).alias('avg_throws_count'),
                fn.COALESCE(fn.SUM(cls.mvp_value), 0).alias('total_mvp'),
                fn.COALESCE(fn.SUM(cls.game_count), 0).alias('total_game_count'),
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
                'flash_teammate_ratio': float(result.flash_teammate_ratio or 0),
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
                'avg_throws_count': float(result.avg_throws_count or 0),
                'total_mvp': result.total_mvp or 0,
                'match_mvp_count': result.match_mvp_count or 0,
                'total_fire_count': result.total_fire_count or 0,
                'total_game_count': result.total_game_count or 0,
            }

        except cls.DoesNotExist:
            logger.info("No records found for the given criteria")
            return None
        except Exception as e:
            logger.error(f"get_match_exploit error: {e}")
            return None

    @classmethod
    def get_external_player_stats(cls, cup_names: List[str]) -> List[Dict[str, Any]]:
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
        }
        average_fields = {
            'avg_kills': cls.kill,
            'avg_deaths': cls.death,
            'avg_assists': cls.assist,
            'avg_rating': cls.rating,
            'avg_pw_rating': cls.pw_rating,
            'avg_adpr': cls.adpr,
            'avg_rws': cls.rws,
            'avg_kast': cls.kast,
            'avg_we': cls.we,
            'avg_headshot_ratio': cls.headshot_ratio,
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

        rows = list(
            cls.select(*select_fields)
            .where(cls.cup_name.in_(cup_names))
            .group_by(cls.player_id)
            .dicts()
        )
        player_ids = [row['player_id'] for row in rows]
        player_map = {
            player.player_id: player
            for player in Player.select().where(Player.player_id.in_(player_ids))
        } if player_ids else {}

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
            row['kd_ratio'] = _ratio(row['total_kills'], row['total_deaths'])
            row['fk_fd_ratio'] = _ratio(row['total_first_kills'], row['total_first_deaths'])
            row['win_rate'] = _ratio(row['win_count'], row['match_count'])
            row['headshot_ratio'] = _ratio(row['total_headshots'], row['total_kills'])
            row['flash_success_ratio'] = _ratio(row['total_flash_success'], row['total_flashes'])
            row['flash_teammate_ratio'] = _ratio(row['total_flash_teammate'], row['total_flashes'])
            row['hit_ratio'] = _ratio(row['total_hit_count'], row['total_fire_count'])

            player = player_map.get(row['player_id'])
            if player:
                row.update({
                    'nickname': player.nickname or row.get('nickname'),
                    'avatar': player.avatar or row.get('avatar'),
                    'alias_name': player.alias_name or '',
                    'steam_id': player.steam_id or '',
                    'live_url': player.live_url or '',
                    'in_library': bool(player.in_library),
                })
            else:
                row.update({
                    'alias_name': '',
                    'steam_id': '',
                    'live_url': '',
                    'in_library': False,
                })
            result.append(row)

        result.sort(key=lambda item: (-item['avg_rating'], item['player_id']))
        return result

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
                fn.COALESCE(fn.AVG(cls.pw_rating), 0).alias('avg_rating'),
                fn.COALESCE(fn.AVG(cls.kill), 0).alias('avg_kills'),
                fn.COALESCE(fn.AVG(cls.death), 0).alias('avg_deaths'),
                fn.COALESCE(fn.AVG(cls.assist), 0).alias('avg_assists'),
                fn.COALESCE(fn.AVG(cls.headshot_ratio), 0).alias('avg_headshot_ratio'),
                fn.COALESCE(fn.AVG(cls.adpr), 0).alias('avg_adpr'),
                fn.COALESCE(fn.SUM(cls.mvp_value), 0).alias('total_mvp'),
                fn.COALESCE(fn.SUM(cls.two_kill), 0).alias('total_2k'),
                fn.COALESCE(fn.SUM(cls.three_kill), 0).alias('total_3k'),
                fn.COALESCE(fn.SUM(cls.four_kill), 0).alias('total_4k'),
                fn.COALESCE(fn.SUM(cls.five_kill), 0).alias('total_5k'),
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
                    'avg_headshot_ratio': float(result.avg_headshot_ratio or 0),
                    'avg_adpr': float(result.avg_adpr or 0),
                    'kd_ratio': kd_ratio,
                    'total_mvp': result.total_mvp or 0,
                    'total_2k': result.total_2k or 0,
                    'total_3k': result.total_3k or 0,
                    'total_4k': result.total_4k or 0,
                    'total_5k': result.total_5k or 0,
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

            return list(
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
