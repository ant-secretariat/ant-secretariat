"""개미비서단 온톨로지 관계사전 시드 로더.

원본은 같은 폴더의 ontology_seed.json 하나다 (scripts/build_seed.py 가 만든다). 이 모듈은 손으로 쓰며 생성하지 않는다.

노출 규칙 (ADR 0008 · 헌법 원칙 IV)
- 노드·엣지는 status == "active" 이고 reviewed 가 True 일 때만 돌려준다.
  Claude 초안(ISSUE·BENEFITS/HURTS·EXPOSED_TO·IMPACTS, status "draft"), 가설과 부호가 어긋난 민감도
  (status "needs_review"), 수집 계획 없는 매크로(status "inactive")는 기본값에서 빠진다.
- 노드의 draft_fields 에 적힌 속성(섹터 경기 성격, 종목 세부 산업 등)도 기본값에서 뺀다.
- include_draft=True 는 검수용이다. inactive 를 뺀 전부와 draft_fields 를 그대로 돌려준다. 주입 경로에서는 쓰지 않는다.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_PATH = Path(__file__).with_name("ontology_seed.json")
NODE_KEYS = {"sectors": "sector_id", "macros": "indicator_id", "issues": "issue_id", "companies_t1": "ticker"}


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def is_exposed(record: dict, include_draft: bool = False) -> bool:
    if include_draft:
        return record["status"] != "inactive"
    return record["status"] == "active" and record["reviewed"] is True


def _public(record: dict, include_draft: bool) -> dict:
    out = copy.deepcopy(record)
    if not include_draft:
        for k in record.get("draft_fields", []):
            out.pop(k, None)
    return out


def nodes(kind: str, include_draft: bool = False) -> dict[str, dict]:
    key = NODE_KEYS[kind]
    return {n[key]: _public(n, include_draft) for n in load()["nodes"][kind] if is_exposed(n, include_draft)}


def edges(kind: str, include_draft: bool = False) -> list[dict]:
    """get_ontology_context 주입과 Judge 경로 검증은 이 함수(기본값)만 쓴다."""
    return [copy.deepcopy(e) for e in load()["edges"][kind] if is_exposed(e, include_draft)]


def company_context(ticker: str, include_draft: bool = False) -> dict:
    """2홉: COMPANY → SECTOR → MACRO(SENSITIVE_TO) + COMPANY ↔ ISSUE.

    민감도는 주기별로 나눠 돌려준다. 일별(corr_daily)과 월별(1달 시차 corr_monthly)은 뜻이 달라 크기를 바로 비교하지 않는다.
    없는 종목이면 빈 dict.
    """
    company = nodes("companies_t1", include_draft).get(ticker)
    if company is None:
        return {}
    sec = company["sector_id"]
    sens = [e for e in edges("sensitive_to", include_draft) if e["src"] == sec]
    issue_nodes = nodes("issues", include_draft)
    issues: dict[str, dict] = {}
    for via, target in (("SECTOR", sec), ("COMPANY", ticker)):  # 종목 엣지가 섹터 엣지를 덮어쓴다
        for e in edges("benefits_hurts", include_draft):
            if e["dst"] == target and e["src"] in issue_nodes:
                issues[e["src"]] = {**issue_nodes[e["src"]], "relation": e["relation"], "strength": e["strength"], "via": via}
    return {
        "company": company,
        "sector": nodes("sectors", include_draft)[sec],
        "sector_sensitivities": {f: [e for e in sens if e["weight_frequency"] == f] for f in ("daily", "monthly")},
        "issues": list(issues.values()),
    }
