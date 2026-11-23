"""ISSUE 노드 근거 후보 뽑기 (사람이 골라 연결하기 전 단계, #61: 자동 연결하지 않음).

    python ontology/seed/scripts/issue_evidence_candidates.py <출력.md> [--per-ticker 3] [--as-of YYYY-MM-DD]

- 이슈마다 EXPOSED_TO로 이어진 종목(최대 3개)에서 "이슈 이름 + 메모"로 문서를 검색해 후보를 모은다.
- 출력 파일에는 리포트·뉴스 본문 일부가 들어가므로 **git 밖에** 둔다(수집 원본 커밋 금지).
- 고른 조각은 ontology/seed/issue_evidence.csv에 chunk_id만 적는다. 시드는 그 CSV만 읽는다.
- 읽기만 한다. DB 주소는 환경변수(backend/.env, data-pipeline/.env)에서 읽고 출력하지 않는다.
"""
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

SEED = Path(__file__).resolve().parents[1]
ROOT = SEED.parents[1]
SNIPPET = 220


def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    load_dotenv(ROOT / "data-pipeline" / ".env")


def candidates(seed: dict, search, per_ticker: int, as_of=None) -> dict[str, list[dict]]:
    """search(query, ticker, top_k, as_of) → results[]. 테스트에서는 가짜 search를 넣는다."""
    exposed = defaultdict(list)
    for e in seed["edges"]["exposed_to"]:
        exposed[e["dst"]].append((e.get("exposure") or 0, e["src"]))
    out = {}
    for issue in seed["nodes"]["issues"]:
        tickers = [tk for _, tk in sorted(exposed[issue["issue_id"]], reverse=True)][:3]
        seen, rows = set(), []
        for tk in tickers:
            for r in search(f"{issue['name']} {issue.get('notes') or ''}".strip(), tk, per_ticker, as_of):
                if r["chunk_id"] in seen:
                    continue
                seen.add(r["chunk_id"])
                rows.append({**r, "ticker": tk})
        out[issue["issue_id"]] = rows
    return out


def to_markdown(seed: dict, found: dict[str, list[dict]]) -> str:
    lines = ["# ISSUE 근거 후보 (git에 올리지 않음)", "",
             "고른 조각은 `ontology/seed/issue_evidence.csv`에 `issue_id,chunk_id,ticker,published_at,decided_by,decided_on`으로 적는다.", ""]
    for issue in seed["nodes"]["issues"]:
        lines += [f"## {issue['issue_id']} — {issue['name']}", f"메모: {issue.get('notes') or ''}", ""]
        for r in found.get(issue["issue_id"], []) or []:
            text = " ".join((r.get("content") or "").split())[:SNIPPET]
            lines.append(f"- [ ] `{r['chunk_id']}` {r['ticker']} · {str(r.get('date') or '')[:10]} · "
                         f"{r.get('document_type')} · {r.get('author_org') or r.get('source') or ''} · {r.get('title') or ''}")
            lines.append(f"  > {text}")
        if not found.get(issue["issue_id"]):
            lines.append("- (후보 없음)")
        lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--per-ticker", type=int, default=3)
    p.add_argument("--as-of")
    a = p.parse_args(argv)
    if a.out.resolve().is_relative_to(ROOT):
        raise SystemExit("후보 파일에는 문서 본문이 들어가서 저장소 밖에 둡니다")
    _load_env()
    sys.path.insert(0, str(ROOT / "data-pipeline"))
    from processing.functions.search_documents import search_documents

    def search(query, ticker, top_k, as_of):
        kw = {"as_of": as_of} if as_of else {}
        return search_documents(query=query, ticker=ticker, top_k=top_k, **kw).get("results") or []

    seed = json.loads((SEED / "ontology_seed.json").read_text(encoding="utf-8"))
    found = candidates(seed, search, a.per_ticker, a.as_of)
    a.out.write_text(to_markdown(seed, found), encoding="utf-8")
    print(f"{a.out}: 이슈 {len(found)}개, 후보 {sum(len(v) for v in found.values())}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
