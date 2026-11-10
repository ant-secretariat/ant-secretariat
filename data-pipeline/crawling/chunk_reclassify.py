"""이미 적재한 청크에 청커의 고지 판별 규칙(is_boilerplate)을 다시 적용한다. PDF를 다시 받지 않는다.

    python -m crawling.chunk_reclassify --dry-run    # 바뀔 청크 수만
    python -m crawling.chunk_reclassify --backup storage/reclassify_ids.json

청커 규칙을 고친 것이 section_type 판별뿐이면 리포트를 다시 자를 필요가 없다. 본문이 같아 청크 ID와 임베딩도 그대로다.
새로 적재하는 리포트는 청커가 같은 규칙을 바로 적용한다.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from crawling.db.postgres import connect
from processing.processors.report_chunker import is_boilerplate

logger = logging.getLogger(__name__)


def reclassify(dry_run: bool = False, backup: str | None = None) -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            "select chunk_id, chunk_type, body from document_chunks where section_type = 'body'"
        ).fetchall()
        changed = [chunk_id for chunk_id, chunk_type, body in rows if is_boilerplate(body, chunk_type)]
        logger.info("본문 청크 %s개 중 고지로 바꿀 청크 %s개", f"{len(rows):,}", f"{len(changed):,}")
        if dry_run or not changed:
            return changed
        if backup:
            Path(backup).parent.mkdir(parents=True, exist_ok=True)
            Path(backup).write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
        with connection.transaction():
            connection.execute(
                "update document_chunks set section_type = 'disclaimer' where chunk_id = any(%s)", (changed,)
            )
    return changed


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    parser = argparse.ArgumentParser(description="청크 고지 판별 다시 적용")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup", default=None, help="바꾼 청크 ID를 저장할 경로 (되돌릴 때 사용)")
    args = parser.parse_args()
    reclassify(args.dry_run, args.backup)


if __name__ == "__main__":
    main()
