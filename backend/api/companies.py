"""프론트엔드 기업 선택/데이터 상태 조회 API."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException

from db import DEFAULT_DB_PATH

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("")
def list_companies() -> dict:
    from processing.config.supported_companies import SUPPORTED_COMPANIES

    return {
        "companies": [
            {
                "ticker": company["ticker"],
                "company": company["company"],
                "sector": company.get("sector", ""),
                "aliases": company.get("aliases", []),
            }
            for company in SUPPORTED_COMPANIES
        ]
    }


@router.get("/{ticker}/data-status")
def read_company_data_status(ticker: str) -> dict:
    from processing.functions.get_available_data_status import get_available_data_status
    from processing.storage.implementations import PlaceholderVectorDB
    from processing.storage.sqlite_db import SQLiteDB

    db_path = Path(os.environ.get("DATABASE_PATH", str(DEFAULT_DB_PATH)))
    try:
        return get_available_data_status(
            ticker=ticker,
            relational_db=SQLiteDB(str(db_path)),
            vector_db=PlaceholderVectorDB(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
