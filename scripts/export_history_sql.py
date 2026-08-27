#!/usr/bin/env python3
"""Export the legacy SQLite database as a PostgreSQL bootstrap data script."""

import argparse
import math
import sqlite3
from pathlib import Path


HISTORY_VERSION = 'data_001_cs_history'
LEGACY_TABLES = (
    'config',
    'match',
    'match_player',
    'player',
    'cup_day_champion',
    'player_title',
)
SEQUENCE_TABLES = (
    'config',
    'match',
    'match_player',
    'cup_day_champion',
    'player_title',
    'season',
    'match_selection',
)
BOOLEAN_COLUMNS = {
    'match_player': {'mvp'},
    'player': {'in_library'},
    'player_title': {'is_active'},
}


def quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def quote_value(value) -> str:
    if value is None:
        return 'NULL'
    if isinstance(value, bool):
        return 'TRUE' if value else 'FALSE'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else 'NULL'
    if isinstance(value, bytes):
        return "decode('%s', 'hex')" % value.hex()
    return "'%s'" % str(value).replace("'", "''")


def table_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f'PRAGMA table_info({quote_identifier(table_name)})').fetchall()
    return [row[1] for row in rows]


def table_rows(connection: sqlite3.Connection, table_name: str, columns: list[str]):
    order_column = 'id' if 'id' in columns else columns[0]
    column_sql = ', '.join(quote_identifier(column) for column in columns)
    return connection.execute(
        f'SELECT {column_sql} FROM {quote_identifier(table_name)} '
        f'ORDER BY {quote_identifier(order_column)}'
    ).fetchall()


def insert_statement(table_name: str, columns: list[str], rows: list[tuple]) -> str:
    if not rows:
        return f'-- {table_name}: no rows\n'
    columns_sql = ', '.join(quote_identifier(column) for column in columns)
    values_sql = ',\n'.join(
        '  (' + ', '.join(quote_value(value) for value in row) + ')'
        for row in rows
    )
    return (
        f'INSERT INTO {quote_identifier(table_name)} ({columns_sql}) VALUES\n'
        f'{values_sql}\nON CONFLICT DO NOTHING;\n'
    )


def derived_seasons(connection: sqlite3.Connection) -> tuple[list[str], list[tuple]]:
    columns = [
        'id', 'created_at', 'updated_at', 'cup_name', 'cup_alias', 'name',
        'match_type', 'start_date', 'end_date', 'status', 'hit_ratio',
    ]
    source_rows = connection.execute(
        '''
        SELECT cup_name, MIN(created_at), MAX(updated_at), MIN(start_time), MAX(end_time)
        FROM "match"
        WHERE cup_name IS NOT NULL AND TRIM(cup_name) <> ''
        GROUP BY cup_name
        ORDER BY cup_name
        '''
    ).fetchall()
    rows = [
        (
            index, created_at, updated_at, cup_name, cup_name, cup_name,
            'official', start_date, end_date, 'archived', 0.6,
        )
        for index, (cup_name, created_at, updated_at, start_date, end_date)
        in enumerate(source_rows, start=1)
    ]
    return columns, rows


def derived_match_selections(connection: sqlite3.Connection) -> tuple[list[str], list[tuple]]:
    columns = [
        'id', 'created_at', 'updated_at', 'match_id', 'season_cup_name',
        'status', 'source_type', 'play_day', 'roster_hit_count', 'note',
    ]
    source_rows = connection.execute(
        '''
        SELECT id, created_at, updated_at, match_id, cup_name, play_day
        FROM "match"
        WHERE cup_name IS NOT NULL AND TRIM(cup_name) <> ''
        ORDER BY id
        '''
    ).fetchall()
    rows = [
        (row_id, created_at, updated_at, match_id, cup_name,
         'approved', 'official', play_day, 0, None)
        for row_id, created_at, updated_at, match_id, cup_name, play_day in source_rows
    ]
    return columns, rows


def export_sql(source_path: Path, output_path: Path) -> dict[str, int]:
    if not source_path.is_file():
        raise FileNotFoundError(f'SQLite source does not exist: {source_path}')

    connection = sqlite3.connect(source_path)
    try:
        existing_tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        missing = set(LEGACY_TABLES) - existing_tables
        if missing:
            raise RuntimeError(f'Legacy database is missing tables: {sorted(missing)}')

        statements = [
            '-- Generated from cs.db by scripts/export_history_sql.py.\n',
            '-- PostgreSQL schema must be initialized before this data script is applied.\n',
            '-- The application imports this file transactionally only when history tables are empty.\n\n',
        ]
        counts = {}
        newest_update = '1970-01-01 00:00:00'

        for table_name in LEGACY_TABLES:
            columns = table_columns(connection, table_name)
            rows = table_rows(connection, table_name, columns)
            boolean_indexes = [
                columns.index(column)
                for column in BOOLEAN_COLUMNS.get(table_name, set())
            ]
            if boolean_indexes:
                normalized_rows = []
                for row in rows:
                    values = list(row)
                    for index in boolean_indexes:
                        values[index] = bool(values[index])
                    normalized_rows.append(tuple(values))
                rows = normalized_rows
            if table_name == 'player':
                if 'live_url' not in columns:
                    columns = [*columns, 'live_url']
                    rows = [(*row, None) for row in rows]
                if 'in_library' not in columns:
                    columns = [*columns, 'in_library']
                    rows = [(*row, True) for row in rows]
            counts[table_name] = len(rows)
            statements.append(insert_statement(table_name, columns, rows))
            statements.append('\n')

            updated_index = columns.index('updated_at') if 'updated_at' in columns else None
            if updated_index is not None:
                for row in rows:
                    if row[updated_index] and str(row[updated_index]) > newest_update:
                        newest_update = str(row[updated_index])

        season_columns, season_rows = derived_seasons(connection)
        counts['season'] = len(season_rows)
        statements.append(insert_statement('season', season_columns, season_rows))
        statements.append('\n')

        selection_columns, selection_rows = derived_match_selections(connection)
        counts['match_selection'] = len(selection_rows)
        statements.append(insert_statement('match_selection', selection_columns, selection_rows))
        statements.append('\n')

        statements.append('-- Keep PostgreSQL sequences ahead of explicitly imported IDs.\n')
        for table_name in SEQUENCE_TABLES:
            table_literal = quote_value(table_name)
            statements.append(
                f"SELECT setval(pg_get_serial_sequence({table_literal}, 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {quote_identifier(table_name)}), 1), "
                f"(SELECT MAX(id) IS NOT NULL FROM {quote_identifier(table_name)}));\n"
            )

        marker_columns = ['created_at', 'updated_at', 'version', 'applied_at']
        marker_rows = [(newest_update, newest_update, HISTORY_VERSION, newest_update)]
        statements.extend(['\n', insert_statement('schema_migrations', marker_columns, marker_rows)])

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(''.join(statements), encoding='utf-8')
        return counts
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path, help='legacy SQLite database')
    parser.add_argument('output', type=Path, help='PostgreSQL SQL output')
    args = parser.parse_args()
    counts = export_sql(args.source, args.output)
    summary = ', '.join(f'{table}={count}' for table, count in counts.items())
    print(f'Wrote {args.output} ({summary})')


if __name__ == '__main__':
    main()
