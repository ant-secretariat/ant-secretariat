"""ECOS 매크로 지표(금리·환율·물가·유가)를 Supabase macro_data에 적재한다.

    python -m crawling.macro_loader --backfill         # 2000년부터 전체 이력 적재
    python -m crawling.macro_loader --daily            # 최근 구간만 다시 받아 갱신

--daily는 일별 지표 45일, 월별 지표 400일을 다시 받아 뒤늦은 수정치도 반영한다.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawling.collectors.macro_data_collector import (
    DEFAULT_ECOS_INDICATORS,
    EcosMacroProvider,
)
from crawling.config.settings import SETTINGS
from crawling.db.postgres import connect, upsert

logger = logging.getLogger(__name__)


BACKFILL_START = date(2000, 1, 1)
UPDATE_COLUMNS = ("indicator_name", "value", "unit", "frequency", "country", "source")


def load(indicators: list[str], date_from: date | None, date_to: date | None) -> None:
    rows = EcosMacroProvider(SETTINGS).collect(
        indicators,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )
    # created_at은 최초 적재 시각으로 남기도록 테이블 기본값에 맡긴다
    for row in rows:
        row.pop("created_at", None)

    with connect() as connection:
        upsert(
            connection,
            "macro_data",
            rows,
            key_columns=["indicator_id", "date"],
            update_columns=UPDATE_COLUMNS,
        )

    counts = Counter(row["indicator_id"] for row in rows)
    for indicator_id in indicators:
        dates = [row["date"] for row in rows if row["indicator_id"] == indicator_id]
        if dates:
            logger.info("%s: %s행 (%s ~ %s)", indicator_id, counts[indicator_id], min(dates), max(dates))
        else:
            logger.warning("%s: 받은 데이터가 없습니다", indicator_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ECOS 매크로 지표 Supabase 적재")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--backfill", action="store_true", help="전체 이력 적재")
    mode.add_argument("--daily", action="store_true", help="최근 구간 갱신")
    parser.add_argument("--start", type=date.fromisoformat, default=BACKFILL_START, help="--backfill 시작일 YYYY-MM-DD")
    parser.add_argument("--date", type=date.fromisoformat, default=None, help="기준일(종료일) YYYY-MM-DD")
    parser.add_argument(
        "--indicators",
        nargs="+",
        choices=list(DEFAULT_ECOS_INDICATORS),
        default=list(DEFAULT_ECOS_INDICATORS),
        help="적재할 지표 (기본: 전체)",
    )
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # httpx는 요청 URL을 INFO로 남기는데, ECOS는 인증키가 URL에 들어간다
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args()
    if not SETTINGS.ecos_api_key:
        raise SystemExit("ECOS_API_KEY가 설정되지 않았습니다 (data-pipeline/.env 확인)")
    load(args.indicators, args.start if args.backfill else None, args.date)


if __name__ == "__main__":
    main()
