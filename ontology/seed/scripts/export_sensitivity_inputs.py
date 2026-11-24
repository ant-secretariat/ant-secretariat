"""ontology_sensitivity_inputs(#67)의 기준일 스냅샷에서 가설 엣지 행만 CSV로 내보낸다 (ADR 0011 6번).

    python ontology/seed/scripts/export_sensitivity_inputs.py 2026-11-23

- 읽기만 한다. SUPABASE_DB_URL은 환경변수(backend/.env 또는 data-pipeline/.env)에서 읽고 출력하지 않는다.
- 출력: ontology/seed/sensitivity_inputs_<as_of>.csv. 시드는 이 파일만 읽어서, DB 없이도 같은 시드를 다시 만들 수 있다.
- 가설 목록(co_hypotheses.py)에 있는 (종목, 지표)만 내보낸다. 표에 없는 쌍은 빠지고, 시드가 needs_review로 둔다.
"""
import csv
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from co_hypotheses import CO_HYPOTHESES  # noqa: E402

COLUMNS = ["as_of", "group_id", "factor", "frequency", "method", "window_start", "window_end",
           "n_obs", "raw", "adjusted", "ci_low", "ci_high", "certain", "p_value", "q_value", "computed_at"]


def _db_url() -> str:
    try:
        from dotenv import load_dotenv
        root = HERE.parents[2]
        load_dotenv(root / "backend" / ".env")
        load_dotenv(root / "data-pipeline" / ".env")
    except ImportError:
        pass
    url = os.getenv("SUPABASE_DB_URL")
    if not url:
        raise SystemExit("SUPABASE_DB_URL이 없습니다 (backend/.env 또는 data-pipeline/.env)")
    return url


def main(as_of: str) -> Path:
    import psycopg

    keys = sorted({f"{tk}:{m}" for tk, m, *_ in CO_HYPOTHESES})
    with psycopg.connect(_db_url()) as conn:
        conn.read_only = True  # 읽기만 한다(실수로 쓰지 않게)
        rows = conn.execute(
            f"select {', '.join(COLUMNS)} from ontology_sensitivity_inputs "
            "where as_of = %s and level = 'ticker' and group_id || ':' || factor = any(%s) order by group_id, factor",
            (as_of, keys)).fetchall()
    out = HERE.parent / f"sensitivity_inputs_{as_of}.csv"
    with out.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        # computed_at(timestamptz)은 ISO 8601로 (같은 기준일을 다시 계산했는지 알 수 있게, 수경 #80 리뷰)
        w.writerows([[v.isoformat(timespec="seconds") if hasattr(v, "isoformat") and k == "computed_at" else v
                      for k, v in zip(COLUMNS, r)] for r in rows])
    print(f"{out.name}: {len(rows)}/{len(keys)}행")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python ontology/seed/scripts/export_sensitivity_inputs.py YYYY-MM-DD")
    main(sys.argv[1])
