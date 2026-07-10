"""Debate/Simulation 작업 상태 및 결과 조회 API."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from db import get_database
from functions.agent_jobs import get_agent_job, list_user_jobs

router = APIRouter(tags=["debate-jobs"])


@router.get("/debate/jobs/{job_id}")
def read_debate_job(job_id: str) -> dict:
    try:
        job = get_agent_job(job_id=job_id, relational_db=get_database())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"job": job}


@router.get("/debate/jobs/{job_id}/result")
def read_debate_result(job_id: str) -> dict:
    try:
        job = get_agent_job(job_id=job_id, relational_db=get_database())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "debate_result": job["debate_result"],
    }


@router.get("/debate/jobs/{job_id}/simulation")
def read_simulation_result(job_id: str) -> dict:
    try:
        job = get_agent_job(job_id=job_id, relational_db=get_database())
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "simulation_result": job["simulation_result"],
    }


@router.get("/users/{user_id}/jobs")
def read_user_jobs(user_id: str, limit: int = Query(default=50, ge=1, le=100)) -> dict:
    return {
        "jobs": list_user_jobs(
            user_id=user_id,
            relational_db=get_database(),
            limit=limit,
        )
    }
