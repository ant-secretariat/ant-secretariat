from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import psycopg
from psycopg import sql

from crawling.config.settings import SETTINGS, Settings


def connect(settings: Settings | None = None) -> psycopg.Connection:
    settings = settings or SETTINGS
    if not settings.supabase_db_url:
        raise RuntimeError("SUPABASE_DB_URL이 설정되지 않았습니다 (data-pipeline/.env 확인)")
    # autocommit: upsert마다 자체 트랜잭션을 열어 임시 테이블이 커밋과 함께 사라지게 한다
    return psycopg.connect(settings.supabase_db_url, autocommit=True)


def upsert(
    connection: psycopg.Connection,
    table: str,
    rows: Iterable[dict[str, Any]],
    key_columns: Sequence[str],
    update_columns: Sequence[str] | None = None,
) -> int:
    """rows를 임시 테이블에 COPY한 뒤 한 번에 INSERT ... ON CONFLICT로 반영한다.

    update_columns를 주면 충돌 시 그 컬럼만 갱신한다. 같은 행을 여러 소스가
    나눠 채우는 경우(예: 시세는 종목별 조회, 거래대금은 날짜별 조회)에 쓴다.
    """
    rows = list(rows)
    if not rows:
        return 0

    columns = list(rows[0].keys())
    if update_columns is None:
        update_columns = [column for column in columns if column not in key_columns]

    column_list = sql.SQL(", ").join(map(sql.Identifier, columns))
    conflict_action = (
        sql.SQL("do update set {}").format(
            sql.SQL(", ").join(
                sql.SQL("{0} = excluded.{0}").format(sql.Identifier(column))
                for column in update_columns
            )
        )
        if update_columns
        else sql.SQL("do nothing")
    )

    with connection.transaction(), connection.cursor() as cursor:
        cursor.execute(
            sql.SQL(
                "create temp table _stage (like {} including defaults) on commit drop"
            ).format(sql.Identifier(table))
        )
        with cursor.copy(
            sql.SQL("copy _stage ({}) from stdin").format(column_list)
        ) as copy:
            for row in rows:
                copy.write_row([row[column] for column in columns])
        cursor.execute(
            sql.SQL(
                "insert into {table} ({columns}) select {columns} from _stage "
                "on conflict ({keys}) {action}"
            ).format(
                table=sql.Identifier(table),
                columns=column_list,
                keys=sql.SQL(", ").join(map(sql.Identifier, key_columns)),
                action=conflict_action,
            )
        )
        return cursor.rowcount
