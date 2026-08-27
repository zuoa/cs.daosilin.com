"""Versioned schema migrations. Applied automatically on startup."""
from datetime import datetime

from ajlog import logger
from config import ADMIN_PASSWORD, ADMIN_USERNAME
from database import (AdminUser, SchemaMigration, _add_column, _column_exists, _table_exists,
                      db, is_postgres)


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


MIGRATIONS = [
    ('001_player_in_library', _m001_player_in_library),
    ('002_season_hit_ratio', _m002_season_hit_ratio),
    ('003_selection_pending', _m003_selection_pending),
    ('004_season_cup_alias', _m004_season_cup_alias),
    ('005_bootstrap_admin', _m005_bootstrap_admin),
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
