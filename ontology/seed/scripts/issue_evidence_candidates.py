"""ISSUE 노드 근거 후보 뽑기 (사람이 골라 연결하기 전 단계, #61: 자동 연결하지 않음).

    python ontology/seed/scripts/issue_evidence_candidates.py <출력.md> [--per-ticker 3] [--as-of YYYY-MM-DD]

- 이슈마다 EXPOSED_TO로 이어진 종목(최대 3개)에서 "이슈 이름 + 핵심 키워드"로 뉴스·리포트를 따로 검색해 후보를 모은다.
  메모 전체를 붙이면 일반 단어(수요·확대 등) 때문에 키워드 검색 점수가 흐려진다(수경 #83 리뷰).
- `--verify`: issue_evidence.csv의 chunk_id가 DB에 있는지, published_at이 맞는지 get_chunks_by_ids로 확인(시드 빌드 밖).
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
DOC_TYPES = ("news", "report")  # 이슈는 대부분 뉴스로 드러나서 종류마다 따로 찾는다
# 검색어에 붙일 핵심 키워드(2~3개). 없으면 이슈 이름만
ISSUE_KEYWORDS = {
    "ISS_AI_MEMORY_DEMAND": "HBM AI서버 메모리", "ISS_MEMORY_PRICE_CYCLE": "D램 가격 낸드 가격",
    "ISS_SEMI_EXPORT_CONTROL": "수출 통제 중국 장비", "ISS_FOUNDRY_COMPETITION": "파운드리 수율 2나노",
    "ISS_AI_POWER_INFRA": "변압기 전력망 데이터센터", "ISS_AI_PCB_DEMAND": "MLB 기판 AI 가속기",
    "ISS_AUTO_US_TARIFF": "자동차 관세 미국", "ISS_EV_DEMAND_SLOWDOWN": "전기차 캐즘 수요 둔화",
    "ISS_BATTERY_CHINA_COMPETITION": "중국 배터리 LFP 가격", "ISS_ESS_DEMAND": "ESS 수주",
    "ISS_SHIPBUILDING_UPCYCLE": "선박 수주 신조선가", "ISS_US_SHIPBUILDING_COOP": "MRO 미국 해군 마스가",
    "ISS_DEFENSE_EXPORT": "방산 수출 계약", "ISS_NUCLEAR_EXPORT": "원전 수주 체코",
    "ISS_RATE_CUT_NIM": "금리 인하 순이자마진", "ISS_PF_CREDIT_RISK": "PF 부실 충당금",
    "ISS_TRADING_VOLUME_BOOM": "거래대금 브로커리지", "ISS_VALUEUP_POLICY": "밸류업 자사주 소각",
    "ISS_GOVERNANCE_REFORM": "상법 개정 지배구조", "ISS_CHINA_CHEM_OVERCAPACITY": "중국 증설 석유화학 공급과잉",
    "ISS_PLATFORM_REGULATION": "플랫폼법 공정위 규제", "ISS_KBEAUTY_EXPORT": "화장품 수출 미국",
    "ISS_KFOOD_EXPORT": "라면 수출", "ISS_BIO_CDMO_DEMAND": "CDMO 바이오시밀러 수주",
    "ISS_PHARMA_US_TARIFF": "의약품 관세", "ISS_FREIGHT_NORMALIZATION": "컨테이너 운임 SCFI",
}


def _load_env() -> None:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    load_dotenv(ROOT / "data-pipeline" / ".env")


def search_query(issue: dict) -> str:
    return f"{issue['name']} {ISSUE_KEYWORDS.get(issue['issue_id'], '')}".strip()


def candidates(seed: dict, search, per_ticker: int, as_of=None) -> dict[str, list[dict]]:
    """search(query, ticker, top_k, as_of, document_type) → results[]. 테스트에서는 가짜 search를 넣는다."""
    exposed = defaultdict(list)
    for e in seed["edges"]["exposed_to"]:
        exposed[e["dst"]].append((e.get("exposure") or 0, e["src"]))
    out = {}
    for issue in seed["nodes"]["issues"]:
        tickers = [tk for _, tk in sorted(exposed[issue["issue_id"]], reverse=True)][:3]
        seen, rows = set(), []
        for tk, dt in [(tk, dt) for tk in tickers for dt in DOC_TYPES]:
            for r in search(search_query(issue), tk, per_ticker, as_of, dt):
                if r["chunk_id"] in seen:
                    continue
                seen.add(r["chunk_id"])
                rows.append({**r, "ticker": tk})
        out[issue["issue_id"]] = rows
    return out


def to_markdown(seed: dict, found: dict[str, list[dict]]) -> str:
    lines = ["# ISSUE 근거 후보 (git에 올리지 않음)", "", f"as_of: {seed.get('_as_of') or '오늘'}", "",
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


def verify(rows: list[dict], get_chunks) -> list[str]:
    """CSV 행 → 문제 목록. get_chunks(ids) → {"chunks": [...], "missing": [...]}."""
    found = get_chunks([r["chunk_id"] for r in rows])
    by_id = {c["chunk_id"]: c for c in found.get("chunks") or []}
    problems = [f"{cid}: DB에 없음" for cid in found.get("missing") or []]
    for r in rows:
        c = by_id.get(r["chunk_id"]) or {}
        date = str(c.get("published_at") or c.get("date") or "")[:10]
        if date and date != r["published_at"]:
            problems.append(f"{r['chunk_id']}: published_at {r['published_at']} ≠ DB {date}")
    return problems


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path, nargs="?")
    p.add_argument("--per-ticker", type=int, default=2)
    p.add_argument("--as-of")
    p.add_argument("--verify", action="store_true", help="issue_evidence.csv를 DB와 대조만 한다")
    a = p.parse_args(argv)
    if a.verify:
        import csv
        _load_env()
        sys.path.insert(0, str(ROOT / "data-pipeline"))
        from processing.functions.get_chunks_by_ids import get_chunks_by_ids
        rows = list(csv.DictReader((SEED / "issue_evidence.csv").open(encoding="utf-8")))
        problems = verify(rows, get_chunks_by_ids) if rows else []
        print("\n".join(problems) or f"issue_evidence.csv {len(rows)}행 확인")
        return 1 if problems else 0
    if a.out is None:
        raise SystemExit("출력 경로가 필요합니다")
    if a.out.resolve().is_relative_to(ROOT):
        raise SystemExit("후보 파일에는 문서 본문이 들어가서 저장소 밖에 둡니다")
    _load_env()
    sys.path.insert(0, str(ROOT / "data-pipeline"))
    from processing.functions.search_documents import search_documents

    def search(query, ticker, top_k, as_of, document_type):
        kw = {"as_of": as_of} if as_of else {}
        res = search_documents(query=query, ticker=ticker, top_k=top_k, document_type=document_type, **kw)
        return res.get("results") or []

    seed = json.loads((SEED / "ontology_seed.json").read_text(encoding="utf-8"))
    seed["_as_of"] = a.as_of
    found = candidates(seed, search, a.per_ticker, a.as_of)
    a.out.write_text(to_markdown(seed, found), encoding="utf-8")
    print(f"{a.out}: 이슈 {len(found)}개, 후보 {sum(len(v) for v in found.values())}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
