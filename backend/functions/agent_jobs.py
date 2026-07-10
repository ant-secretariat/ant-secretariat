"""Debate/Simulation 비동기 작업 상태 저장 함수."""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from db import Database, utc_now

JOB_STATUSES = {
    "queued",
    "running",
    "debate_completed",
    "simulation_running",
    "completed",
    "failed",
}


def _dumps(value: Any) -> str:
    return json.dumps(value or {}, ensure_ascii=False, default=str)


def _loads(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {}


def _row_to_job(row: dict[str, Any], *, include_results: bool = True) -> dict[str, Any]:
    job = {
        "job_id": row["job_id"],
        "user_id": row["user_id"],
        "job_type": row["job_type"],
        "ticker": row["ticker"],
        "company": row["company"],
        "sector": row["sector"],
        "status": row["status"],
        "error_message": row["error_message"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "request": _loads(row["request_json"]),
    }
    if include_results:
        job["debate_result"] = _loads(row["debate_result_json"])
        job["simulation_result"] = _loads(row["simulation_result_json"])
    return job


def create_agent_job(
    *,
    user_id: str,
    job_type: str,
    ticker: str,
    company: str,
    sector: str = "",
    request: Optional[dict[str, Any]] = None,
    relational_db: Database,
) -> dict[str, Any]:
    if job_type != "debate":
        raise ValueError(f"지원하지 않는 job_type입니다: {job_type}")

    now = utc_now()
    job_id = f"{job_type}_{uuid.uuid4().hex}"
    with relational_db.connect() as connection:
        connection.execute(
            """
            INSERT INTO agent_jobs (
                job_id, user_id, job_type, ticker, company, sector, status,
                request_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?)
            """,
            (
                job_id,
                user_id,
                job_type,
                ticker,
                company,
                sector,
                _dumps(request),
                now,
                now,
            ),
        )
    return get_agent_job(job_id=job_id, relational_db=relational_db)


def get_agent_job(
    *,
    job_id: str,
    relational_db: Database,
    include_results: bool = True,
) -> dict[str, Any]:
    with relational_db.connect() as connection:
        row = connection.execute(
            "SELECT * FROM agent_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if not row:
        raise ValueError(f"작업을 찾을 수 없습니다: {job_id}")
    return _row_to_job(dict(row), include_results=include_results)


def list_user_jobs(
    *,
    user_id: str,
    relational_db: Database,
    limit: int = 50,
) -> list[dict[str, Any]]:
    with relational_db.connect() as connection:
        rows = connection.execute(
            """
            SELECT * FROM agent_jobs
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    return [_row_to_job(dict(row), include_results=False) for row in rows]


def update_agent_job_status(
    *,
    job_id: str,
    status: str,
    relational_db: Database,
    error_message: str = "",
) -> dict[str, Any]:
    if status not in JOB_STATUSES:
        raise ValueError(f"지원하지 않는 job status입니다: {status}")

    with relational_db.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE agent_jobs
            SET status = ?, error_message = ?, updated_at = ?
            WHERE job_id = ?
            """,
            (status, error_message, utc_now(), job_id),
        )
    if cursor.rowcount == 0:
        raise ValueError(f"작업을 찾을 수 없습니다: {job_id}")
    return get_agent_job(job_id=job_id, relational_db=relational_db)


def save_debate_result(
    *,
    job_id: str,
    debate_result: dict[str, Any],
    relational_db: Database,
) -> dict[str, Any]:
    with relational_db.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE agent_jobs
            SET status = 'debate_completed',
                debate_result_json = ?,
                error_message = '',
                updated_at = ?
            WHERE job_id = ?
            """,
            (_dumps(debate_result), utc_now(), job_id),
        )
    if cursor.rowcount == 0:
        raise ValueError(f"작업을 찾을 수 없습니다: {job_id}")
    return get_agent_job(job_id=job_id, relational_db=relational_db)


def save_simulation_result(
    *,
    job_id: str,
    simulation_result: dict[str, Any],
    relational_db: Database,
) -> dict[str, Any]:
    with relational_db.connect() as connection:
        cursor = connection.execute(
            """
            UPDATE agent_jobs
            SET status = 'completed',
                simulation_result_json = ?,
                error_message = '',
                updated_at = ?
            WHERE job_id = ?
            """,
            (_dumps(simulation_result), utc_now(), job_id),
        )
    if cursor.rowcount == 0:
        raise ValueError(f"작업을 찾을 수 없습니다: {job_id}")
    return get_agent_job(job_id=job_id, relational_db=relational_db)
