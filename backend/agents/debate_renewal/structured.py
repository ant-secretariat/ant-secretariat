"""데이터 묶음(get_agent_context, debate + intent) → 토론 근거 행·지표 자리표시자 값.

- 문서(`documents.results`)는 그대로 근거 행이다.
- 지표(`metrics`): 값과 `display`가 둘 다 있으면 근거 행 + `{{metric_id}}` 자리표시자 값(display로 치환, #84 Q1·Q2).
  `loss_making`·`capital_impaired`·`not_applicable_financials`는 "값이 없는 이유"가 사실이라 사실 문장 근거로 넣는다.
  `metric_unavailable`은 조회 실패라(#108 리뷰) 근거에서 빼고 `failures`에 남긴다. 나머지 사유는 조용히 뺀다.
- 블록(`target_price`·`financials`·`disclosures`·`macro`·`index`·`sensitivities`): 근거 행 하나씩. 본문은 LLM이
  읽을 요약 문장이다(60일 시계열 전체는 넣지 않음, #109 리뷰). `error`는 조회 실패로 `failures`, `reason`은 뺀다.
- 근거 ID(chunk_id)는 데이터 쪽이 붙인 `metric:…`·`block:…`를 그대로 쓴다. 같은 지표가 여러 아젠다에 있으면 하나로 합쳐진다.
- 이전 호출 방식(문서 results[] 목록만)도 받는다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence, Union

# 값이 없는 이유 자체가 사실인 사유 → 근거 문장
REASON_FACTS = {
    "loss_making": "직전 사업연도 순이익이 적자라 계산되지 않음",
    "capital_impaired": "자본잠식 상태라 계산되지 않음",
    "not_applicable_financials": "금융업이라 이 지표는 의미가 없음",
}
QUERY_FAILURE = "metric_unavailable"
BLOCK_TITLES = {"target_price": "목표주가 컨센서스", "financials": "분기 재무(최근 8분기)", "disclosures": "최근 공시",
                "macro": "매크로 지표", "index": "시장 지수", "sensitivities": "매크로 민감도(시장 효과를 뺀 값)"}
_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z0-9_]+)\s*\}\}")


@dataclass
class AgendaContext:
    rows: list[dict] = field(default_factory=list)          # 근거 행(문서 + 지표 + 블록)
    metrics: dict[str, str] = field(default_factory=dict)   # metric_id → display (자리표시자 목록)
    failures: list[str] = field(default_factory=list)       # 조회 실패: "metric:per", "block:financials"
    widened: bool = False                                   # 아젠다 문서가 없어 다른 종류로 넓혀 찾음


def from_bundle(fetched: Union[Mapping[str, Any], Sequence[Mapping[str, Any]]]) -> AgendaContext:
    if not isinstance(fetched, Mapping):
        return AgendaContext(rows=list(fetched))
    docs = fetched.get("documents") or {}
    ctx = AgendaContext(rows=list(docs.get("results") or []), widened=bool(docs.get("widened")))
    for m in fetched.get("metrics") or []:
        _add_metric(ctx, m)
    for name, title in BLOCK_TITLES.items():
        block = fetched.get(name)
        if not isinstance(block, Mapping):
            continue
        if block.get("error"):
            ctx.failures.append(f"block:{name}")
        elif block.get("chunk_id"):
            ctx.rows.append(_row(block["chunk_id"], title, block.get("source"), block.get("as_of"), _BLOCK_TEXT[name](block)))
    return ctx


def _add_metric(ctx: AgendaContext, m: Mapping[str, Any]) -> None:
    name, reason = m.get("name") or m.get("metric_id"), m.get("reason")
    if m.get("value") is not None and m.get("display"):
        ctx.metrics[m["metric_id"]] = m["display"]
        basis = f" ({m['basis']})" if m.get("basis") else ""
        text = f"{name}: {m['display']}{basis}. 주장에 쓸 때는 {{{{{m['metric_id']}}}}}로 쓴다."
    elif reason in REASON_FACTS:
        text = f"{name}: 값 없음 — {REASON_FACTS[reason]}."
    else:
        if reason == QUERY_FAILURE:
            ctx.failures.append(f"metric:{m.get('metric_id')}")
        return
    if m.get("chunk_id"):
        ctx.rows.append(_row(m["chunk_id"], name, m.get("source"), m.get("as_of"), text))


def _row(chunk_id: str, title: str, source: Optional[str], as_of: Optional[str], content: str) -> dict:
    return {"chunk_id": chunk_id, "document_type": "structured", "title": title, "source": source or "정형 데이터",
            "date": as_of or "", "content": content}


def fill(text: str, values: Mapping[str, str]) -> str:
    """{{metric_id}}를 display로 바꾼다. 목록에 없는 자리표시자는 남겨 L1이 잡게 한다."""
    return _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def fill_all(value: Any, values: Mapping[str, str]) -> Any:
    """dict·list 안의 모든 문자열에 fill. pydantic 모델은 model_dump() 결과에 쓴다."""
    if not values:
        return value
    if isinstance(value, str):
        return fill(value, values)
    if isinstance(value, list):
        return [fill_all(v, values) for v in value]
    if isinstance(value, dict):
        return {k: fill_all(v, values) for k, v in value.items()}
    return value


# --- 블록 요약 문장 -----------------------------------------------------------

def _won(v) -> str:
    return f"{v:,.0f}원" if isinstance(v, (int, float)) else "알 수 없음"


def _big(v) -> str:
    """재무 금액(원) → 조·억 원. get_metric display와 같은 표기(−1.17조 원)."""
    if not isinstance(v, (int, float)):
        return "알 수 없음"
    if abs(v) >= 10**12:
        return f"{v / 10**12:,.2f}".rstrip("0").rstrip(".") + "조 원"
    return f"{v / 10**8:,.0f}억 원"


def _target_price(b: Mapping) -> str:
    c, out = b.get("consensus") or {}, []
    if c.get("avg_target_price"):
        out.append(f"컨센서스 평균 목표가 {_won(c['avg_target_price'])}(최저 {_won(c.get('min_target_price'))}, "
                   f"최고 {_won(c.get('max_target_price'))}, {c.get('broker_count')}곳)")
    if b.get("upside_pct") is not None:
        out.append(f"상승여력 {b['upside_pct']:+}% — {b.get('upside_basis') or ''}".rstrip(" —"))
    r = b.get("revisions") or {}
    if r:
        out.append(f"최근 {r.get('window_days')}일 목표가 개정: 상향 {r.get('up', 0)}·하향 {r.get('down', 0)}·"
                   f"유지 {r.get('unchanged', 0)}·신규 {r.get('new', 0)}")
    out += [f"{o.get('published_at')} {o.get('broker')} {o.get('opinion') or ''} 목표가 {_won(o.get('target_price'))}"
            for o in (b.get("opinions") or [])[:5]]
    return ". ".join(out)


def _financials(b: Mapping) -> str:
    out = [b.get("basis") or ""]
    for r in (b.get("records") or [])[:8]:
        out.append(f"{r.get('period')}: 매출 {_big(r.get('revenue'))}, 영업이익 {_big(r.get('operating_income'))}, "
                   f"순이익 {_big(r.get('net_income'))}, 영업이익률 {r.get('operating_margin')}%, 부채비율 {r.get('debt_ratio')}%")
    return ". ".join(x for x in out if x)


def _disclosures(b: Mapping) -> str:
    items = [f"{d.get('date')} {d.get('title')}" for d in b.get("disclosures") or []]
    return f"최근 {b.get('window_days')}일 {b.get('total', len(items))}건: " + "; ".join(items)


def _macro(b: Mapping) -> str:
    out = []
    for i in b.get("indicators") or []:
        latest = i.get("latest") or {}
        out.append(f"{i.get('indicator_name')} {latest.get('value')} {i.get('unit') or ''}({latest.get('date')})")
    return "; ".join(out)


def _index(b: Mapping) -> str:
    return "; ".join(f"{i.get('index_name')} {(i.get('latest') or {}).get('close')}"
                     f"({(i.get('latest') or {}).get('date')}, {b.get('days')}거래일 전 대비 {i.get('change_pct')}%)"
                     for i in b.get("indexes") or [])


def _sensitivities(b: Mapping) -> str:
    sure = [f"{f.get('factor')}({f.get('frequency')}) 편상관 {f.get('adjusted')}" for f in b.get("factors") or []
            if f.get("certain")]
    head = "뚜렷한 관계: " + ", ".join(sure) if sure else "뚜렷한 관계가 있는 요인 없음"
    return f"{head}. 나머지 요인은 뚜렷한 관계가 없다. {b.get('caution') or ''}".strip()


_BLOCK_TEXT = {"target_price": _target_price, "financials": _financials, "disclosures": _disclosures,
               "macro": _macro, "index": _index, "sensitivities": _sensitivities}
