"""Versioned schema migrations. Applied automatically on startup."""
from datetime import datetime

from ajlog import logger
from config import ADMIN_PASSWORD, ADMIN_USERNAME
from database import (AdminUser, DemoAnalysis, DemoCredential, DemoPlayerStats,
                      PlayerPerfectRankHistory, PlayerSeasonSummary,
                      SchemaMigration, _add_column, _column_exists, _table_exists,
                      backfill_current_perfect_rank_history, db, is_postgres)


def _applied(version: str) -> bool:
    return SchemaMigration.select().where(SchemaMigration.version == version).exists()


def _mark(version: str) -> None:
    SchemaMigration.create(version=version, applied_at=datetime.now())
    logger.info(f"schema migration applied: {version}")


def _m001_player_in_library():
    if _table_exists('player') and not _column_exists('player', 'in_library'):
        ddl = 'BOOLEAN DEFAULT FALSE' if is_postgres() else 'INTEGER DEFAULT 0'
        _add_column('player', 'in_library', ddl)
        db.execute_sql('UPDATE player SET in_library = TRUE') if is_postgres() else db.execute_sql(
            'UPDATE player SET in_library = 1')
        logger.info('player.in_library 已补列，现有玩家标为库内')


def _m002_season_hit_ratio():
    if _table_exists('season') and not _column_exists('season', 'hit_ratio'):
        _add_column('season', 'hit_ratio', 'DOUBLE PRECISION DEFAULT 0.6' if is_postgres() else 'REAL DEFAULT 0.6')
        db.execute_sql('UPDATE season SET hit_ratio = 0.6 WHERE hit_ratio IS NULL')
        logger.info('season.hit_ratio 已补列')


def _m003_selection_pending():
    if _table_exists('match_selection'):
        db.execute_sql("UPDATE match_selection SET status = 'approved' WHERE status = 'pending'")


def _m004_season_cup_alias():
    if _table_exists('season') and not _column_exists('season', 'cup_alias'):
        _add_column('season', 'cup_alias', 'VARCHAR(128)')
        db.execute_sql('UPDATE season SET cup_alias = COALESCE(name, cup_name) WHERE cup_alias IS NULL')
        logger.info('season.cup_alias 已补列')


def _m005_bootstrap_admin():
    if AdminUser.select().count() > 0:
        return
    from werkzeug.security import generate_password_hash
    password = ADMIN_PASSWORD or 'admin1005'
    AdminUser.create(
        username=ADMIN_USERNAME or 'admin',
        password_hash=generate_password_hash(password),
    )
    logger.info(f'已创建初始管理员账号 {ADMIN_USERNAME or "admin"}，请登录后尽快改密')


def _m006_player_live_url():
    if _table_exists('player') and not _column_exists('player', 'live_url'):
        _add_column('player', 'live_url', 'VARCHAR(500)')
        logger.info('player.live_url 已补列')


def _m007_season_champion_enabled():
    if _table_exists('season') and not _column_exists('season', 'champion_enabled'):
        ddl = 'BOOLEAN DEFAULT FALSE' if is_postgres() else 'INTEGER DEFAULT 0'
        _add_column('season', 'champion_enabled', ddl)
        # 仅已有冠军记录的历史赛季继续开启，练习赛等现有赛季默认关闭。
        enabled = 'TRUE' if is_postgres() else '1'
        db.execute_sql(
            f'UPDATE season SET champion_enabled = {enabled} '
            'WHERE EXISTS (SELECT 1 FROM cup_day_champion c WHERE c.cup_name = season.cup_name)'
        )
        logger.info('season.champion_enabled 已补列，已有冠军记录的历史赛季保持开启')


def _m008_player_avatar_sources():
    if not _table_exists('player'):
        return
    if not _column_exists('player', 'avatar_source'):
        _add_column('player', 'avatar_source', "VARCHAR(16) DEFAULT 'wanmei'")
    if not _column_exists('player', 'wanmei_avatar'):
        _add_column('player', 'wanmei_avatar', 'VARCHAR(500)')
    if not _column_exists('player', 'steam_avatar'):
        _add_column('player', 'steam_avatar', 'VARCHAR(500)')
    if not _column_exists('player', 'live_avatar'):
        _add_column('player', 'live_avatar', 'VARCHAR(500)')
    db.execute_sql("UPDATE player SET avatar_source = 'wanmei' WHERE avatar_source IS NULL")
    db.execute_sql(
        "UPDATE player SET wanmei_avatar = avatar "
        "WHERE wanmei_avatar IS NULL AND avatar IS NOT NULL"
    )
    logger.info('player 头像来源与分类头像字段已补齐')


def _m009_player_perfect_rank():
    if not _table_exists('player'):
        return
    if not _column_exists('player', 'perfect_score'):
        _add_column('player', 'perfect_score', 'INTEGER')
    if not _column_exists('player', 'perfect_level'):
        _add_column('player', 'perfect_level', 'VARCHAR(16)')
    if not _column_exists('player', 'perfect_rank_updated_at'):
        ddl = 'TIMESTAMP' if is_postgres() else 'DATETIME'
        _add_column('player', 'perfect_rank_updated_at', ddl)
    logger.info('player 完美天梯分、段位与更新时间字段已补齐')


def _m010_advanced_match_stats():
    if _table_exists('match') and not _column_exists('match', 'notes'):
        _add_column('match', 'notes', 'TEXT')
    if not _table_exists('match_player'):
        return
    integer_columns = ('trade_frag_count', 'grenade_damage', 'inferno_damage')
    for column in integer_columns:
        if not _column_exists('match_player', column):
            _add_column('match_player', column, 'INTEGER DEFAULT 0')
        db.execute_sql(f'UPDATE match_player SET {column} = 0 WHERE {column} IS NULL')
    if not _column_exists('match_player', 'kill_map'):
        _add_column('match_player', 'kill_map', 'TEXT')
    logger.info('比赛原始详情、补枪、道具伤害与对位击杀字段已补齐')


def _m011_demo_analysis():
    db.create_tables([DemoCredential, DemoAnalysis, DemoPlayerStats], safe=True)
    logger.info('Demo 凭证、任务状态与选手事件统计表已创建')


def _m012_player_season_summary():
    db.create_tables([PlayerSeasonSummary], safe=True)
    logger.info('选手赛季 AI 点评表已创建')


def _m013_player_perfect_rank_history():
    db.create_tables([PlayerPerfectRankHistory], safe=True)
    backfilled = backfill_current_perfect_rank_history()
    logger.info(f'选手完美天梯分历史采样表已创建，补录 {backfilled} 条当前分数')


MIGRATIONS = [
    ('001_player_in_library', _m001_player_in_library),
    ('002_season_hit_ratio', _m002_season_hit_ratio),
    ('003_selection_pending', _m003_selection_pending),
    ('004_season_cup_alias', _m004_season_cup_alias),
    ('005_bootstrap_admin', _m005_bootstrap_admin),
    ('006_player_live_url', _m006_player_live_url),
    ('007_season_champion_enabled', _m007_season_champion_enabled),
    ('008_player_avatar_sources', _m008_player_avatar_sources),
    ('009_player_perfect_rank', _m009_player_perfect_rank),
    ('010_advanced_match_stats', _m010_advanced_match_stats),
    ('011_demo_analysis', _m011_demo_analysis),
    ('012_player_season_summary', _m012_player_season_summary),
    ('013_player_perfect_rank_history', _m013_player_perfect_rank_history),
]


def run_migrations():
    SchemaMigration.create_table(safe=True)
    AdminUser.create_table(safe=True)
    for version, fn in MIGRATIONS:
        if _applied(version):
            continue
        with db.atomic():
            fn()
            _mark(version)
