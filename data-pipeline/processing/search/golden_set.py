"""문서 검색 골든셋을 DB에 넣고, 검색 방식별 점수를 잰다 (기획서 v2 7절).

    python -m processing.search.golden_set import golden.json --snapshot 2026-11-09-v1 --reviewer 수경 --reviewed G01-G14
    python -m processing.search.golden_set evaluate --snapshot 2026-11-09-v1
    python -m processing.search.golden_set evaluate --snapshot 2026-11-09-v1 --reviewed-only

- 골든셋 JSON: [{"id", "question_type", "query", "ticker", "as_of", "expected_chunk_ids", "excluded",
  "labeled_by", "note"}]. 리포트 본문은 넣지 않는다
- 평가 지표: Hit@5, Hit@10(정답이 하나라도 있나), Recall@10(정답 중 찾은 비율), nDCG@10(정답의 순위), MRR
- 의미·하이브리드 평가는 질문마다 Upstage 임베딩을 1번 부른다 (질문 30개에 1원 미만)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

MODES = ("bm25", "vector", "hybrid")
TOP_K = 10


def golden_rows(items: list[dict], snapshot: str, reviewed_ids: set[str], default_reviewer: str) -> list[dict]:
    """골든셋 JSON → search_golden_set 행. 제외 표시(excluded)된 문항은 is_active=false로 남긴다."""
    rows = []
    for item in items:
        chunk_ids = list(dict.fromkeys(item["expected_chunk_ids"]))
        rows.append(
            {
                "golden_id": item["id"],
                "snapshot_tag": snapshot,
                "query": item["query"],
                "ticker": item.get("ticker") or None,
                "as_of": item.get("as_of") or None,
                "question_type": item["question_type"],
                "expected_chunk_ids": chunk_ids,
                "expected_doc_ids": list(dict.fromkeys(chunk_id.split(":")[0] for chunk_id in chunk_ids)),
                "labeled_by": item.get("labeled_by") or default_reviewer,
                "reviewed": item["id"] in reviewed_ids,
                "is_active": not item.get("excluded", False),
                "note": item.get("note") or None,
            }
        )
    return rows


def id_range(text: str | None) -> set[str]:
    """'G01-G14,G20' → {'G01', ..., 'G14', 'G20'}."""
    ids: set[str] = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-")
            prefix = start.rstrip("0123456789")
            width = len(start) - len(prefix)
            ids |= {f"{prefix}{n:0{width}d}" for n in range(int(start[len(prefix):]), int(end[len(prefix):]) + 1)}
        else:
            ids.add(part)
    return ids


def metrics(ranked: list[str], relevant: set[str], k: int = TOP_K) -> dict:
    first = next((rank for rank, chunk_id in enumerate(ranked[:k], start=1) if chunk_id in relevant), None)
    dcg = sum(1 / math.log2(rank + 1) for rank, chunk_id in enumerate(ranked[:k], start=1) if chunk_id in relevant)
    ideal = sum(1 / math.log2(rank + 1) for rank in range(1, min(len(relevant), k) + 1))
    return {
        "hit5": float(bool(first and first <= 5)),
        "hit10": float(first is not None),
        "recall10": len(relevant & set(ranked[:k])) / len(relevant) if relevant else 0.0,
        "ndcg10": dcg / ideal if ideal else 0.0,
        "mrr": 1 / first if first else 0.0,
    }


def import_golden(path: str, snapshot: str, reviewed: str | None, reviewer: str) -> int:
    from crawling.db.postgres import connect, upsert

    items = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = golden_rows(items, snapshot, id_range(reviewed), reviewer)
    with connect() as connection:
        missing = connection.execute(
            "select x from unnest(%s::text[]) x where x not in (select chunk_id from document_chunks)",
            ([chunk_id for row in rows for chunk_id in row["expected_chunk_ids"]],),
        ).fetchall()
        if missing:
            raise SystemExit(f"document_chunks에 없는 정답 청크 {len(missing)}개: {[m[0] for m in missing[:5]]}")
        upsert(connection, "search_golden_set", rows, key_columns=["golden_id"])
    print(f"골든셋 {len(rows)}문항 저장 (snapshot={snapshot}, 검토 완료 {sum(r['reviewed'] for r in rows)}문항)")
    return len(rows)


def evaluate(snapshot: str, modes: tuple[str, ...] = MODES, reviewed_only: bool = False) -> list[dict]:
    from psycopg.rows import dict_row

    from crawling.db.postgres import connect
    from processing.search.chunk_search import search_chunks

    results = []
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            golden = cursor.execute(
                """
                select golden_id, query, ticker, as_of, question_type, expected_chunk_ids
                from search_golden_set
                where snapshot_tag = %s and is_active and cardinality(expected_chunk_ids) > 0
                  and (not %s or reviewed)
                order by golden_id
                """,
                (snapshot, reviewed_only),
            ).fetchall()
        for item in golden:
            relevant = set(item["expected_chunk_ids"])
            as_of = item["as_of"].isoformat() if item["as_of"] else None
            for mode in modes:
                found, used = search_chunks(connection, item["query"], ticker=item["ticker"], as_of=as_of, top_k=TOP_K, mode=mode)
                results.append({"golden_id": item["golden_id"], "question_type": item["question_type"], "mode": mode,
                                "used_mode": used, **metrics([r["chunk_id"] for r in found], relevant)})
    return results


def summary(results: list[dict]) -> str:
    def mean(rows, key):
        return sum(row[key] for row in rows) / len(rows) if rows else 0.0

    modes = list(dict.fromkeys(row["mode"] for row in results))
    lines = [f"문항 {len({row['golden_id'] for row in results})}개, 상위 {TOP_K}개 기준", "",
             f"{'방식':8}{'Hit@5':>7}{'Hit@10':>8}{'Recall@10':>11}{'nDCG@10':>9}{'MRR':>7}"]
    for mode in modes:
        rows = [row for row in results if row["mode"] == mode]
        lines.append(f"{mode:8}{mean(rows, 'hit5'):7.2f}{mean(rows, 'hit10'):8.2f}{mean(rows, 'recall10'):11.2f}"
                     f"{mean(rows, 'ndcg10'):9.2f}{mean(rows, 'mrr'):7.2f}")
    lines += ["", "유형별 nDCG@10", f"{'유형':16}" + "".join(f"{mode:>8}" for mode in modes)]
    for kind in dict.fromkeys(row["question_type"] for row in results):
        lines.append(f"{kind:16}" + "".join(
            f"{mean([r for r in results if r['question_type'] == kind and r['mode'] == mode], 'ndcg10'):8.2f}" for mode in modes))
    fallback = [row["golden_id"] for row in results if row["used_mode"] != row["mode"]]
    lines += ["", "상위 10개에 정답이 없는 문항"]
    lines += [f"  {mode}: {[r['golden_id'] for r in results if r['mode'] == mode and not r['hit10']]}" for mode in modes]
    if fallback:
        lines.append(f"주의: 질문 임베딩 실패로 BM25로 대신한 문항 {sorted(set(fallback))}")
    return "\n".join(lines)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="문서 검색 골든셋")
    commands = parser.add_subparsers(dest="command", required=True)
    load = commands.add_parser("import", help="골든셋 JSON을 DB에 넣는다")
    load.add_argument("path")
    load.add_argument("--snapshot", required=True)
    load.add_argument("--reviewed", default=None, help="사람이 검토한 문항 (예: G01-G14)")
    load.add_argument("--reviewer", default="claude", help="labeled_by가 없을 때 쓸 이름")
    run = commands.add_parser("evaluate", help="검색 방식별 점수")
    run.add_argument("--snapshot", required=True)
    run.add_argument("--modes", nargs="+", default=list(MODES), choices=MODES)
    run.add_argument("--reviewed-only", action="store_true", help="사람이 검토한 문항만")
    run.add_argument("--save", default=None, help="문항별 결과를 JSON으로 저장할 경로")
    args = parser.parse_args()
    if args.command == "import":
        import_golden(args.path, args.snapshot, args.reviewed, args.reviewer)
        return
    results = evaluate(args.snapshot, tuple(args.modes), args.reviewed_only)
    print(summary(results))
    if args.save:
        Path(args.save).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
