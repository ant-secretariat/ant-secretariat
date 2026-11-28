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
                "macro": "매크로 지표", "index": "시장 지수", "sensitivities": "매크로 민감도(시장 효과를 뺀 값)",
                # 계산 근거 블록(get_derived_snapshot, #133). 그 아젠다 metrics에 있는 값은 데이터 쪽이 이미 뺐다
                "valuation": "밸류에이션 위치(과거·업종 대비)", "price_trend": "주가 흐름",
                "fundamental_trend": "최근 분기 실적 추세", "flow": "투자자별 수급"}
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
        # 값이 없는 항목은 빼서 LLM이 "None%"를 숫자처럼 쓰지 않게 한다(#120 리뷰). 금융업 매출 계정 없음 등
        parts = [f"{label} {_big(r[key])}" for label, key in (("매출", "revenue"), ("영업이익", "operating_income"),
                                                               ("순이익", "net_income")) if r.get(key) is not None]
        parts += [f"{label} {r[key]}%" for label, key in (("영업이익률", "operating_margin"), ("부채비율", "debt_ratio"))
                  if r.get(key) is not None]
        if r.get("debt_ratio") is None and r.get("debt_ratio_note") in REASON_FACTS:
            parts.append(f"부채비율 값 없음({REASON_FACTS[r['debt_ratio_note']]})")
        out.append(f"{r.get('period')}: " + (", ".join(parts) or "값 없음"))
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


def _pct(v, signed: bool = True) -> Optional[str]:
    if not isinstance(v, (int, float)):
        return None
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _join(parts) -> str:
    """값이 없는(None) 칸은 빼고 이어 붙인다. LLM이 "None"을 숫자처럼 쓰지 않게(#120 리뷰)."""
    return ", ".join(p for p in parts if p)


def _with(label: str, value: Optional[str]) -> Optional[str]:
    return f"{label} {value}" if value else None


def _valuation_pos(b: Mapping) -> str:
    sector = f"업종({b.get('sector')}, {b.get('sector_count')}종목)" if b.get("sector") else "업종"
    out = [
        _with("PER", f"{b['per']}배" if b.get("per") is not None else None),
        _with("PBR", f"{b['pbr']}배" if b.get("pbr") is not None else None),
        _with("PER 과거 3년 백분위", _pct(b.get("per_percentile_3y"), signed=False)),
        _with("PBR 과거 3년 백분위", _pct(b.get("pbr_percentile_3y"), signed=False)),
        _with(f"{sector} 중앙값", "·".join(f"{k} {b[f]}배" for k, f in (("PER", "sector_per_median"), ("PBR", "sector_pbr_median"))
                                         if b.get(f) is not None) or None),
        _with("업종 대비 PER", _pct(b.get("per_vs_sector_pct"))),
        _with("업종 대비 PBR", _pct(b.get("pbr_vs_sector_pct"))),
        _with("배당수익률", _pct(b.get("dividend_yield"), signed=False)),
    ]
    return ". ".join(x for x in (_join(out), b.get("basis")) if x)


def _price_trend(b: Mapping) -> str:
    vol = lambda v: f"{v * 100:.1f}%" if isinstance(v, (int, float)) else None  # 소수(0.25 = 25%)
    out = [
        _with("종가", _won(b["close"]) if b.get("close") is not None else None),
        _with("수익률 1주", _pct(b.get("return_1w_pct"))),
        _with("1개월", _pct(b.get("return_1m_pct"))),
        _with("1개월 지수 대비 초과", _pct(b.get("excess_return_1m_pct"))),
        _with("3개월", _pct(b.get("return_3m_pct"))),
        _with("3개월 지수 대비 초과", _pct(b.get("excess_return_3m_pct"))),
        _with("변동성(연율) 1개월", vol(b.get("volatility_1m"))),
        _with("3개월", vol(b.get("volatility_3m"))),
        _with("시장 변동성 상위 20% 기준", vol(b.get("volatility_1m_market_threshold"))),
        _with("52주 위치(0=최저, 1=최고)", str(b["position_52w"]) if b.get("position_52w") is not None else None),
        _with("52주 고점 대비", _pct(b.get("drawdown_from_52w_high_pct"))),
    ]
    return ". ".join(x for x in (_join(out), b.get("note_52w")) if x)


def _fundamental_trend(b: Mapping) -> str:
    head = f"{b.get('period')}({b.get('fs_div') or '기준 미상'}, 공시 {b.get('disclosed_at')})"
    parts = []
    for label, key in (("매출", "revenue"), ("영업이익", "operating_income"), ("순이익", "net_income")):
        if b.get(key) is None:
            continue
        changes = _join([_with("전년 대비", _pct(b.get(f"{key}_yoy_pct"))), _with("전분기 대비", _pct(b.get(f"{key}_qoq_pct")))])
        notes = _join([b.get(f"{key}_yoy_note"), b.get(f"{key}_qoq_note")])  # 흑자전환·적자지속 등
        extra = _join([changes, notes])
        parts.append(f"{label} {_big(b[key])}" + (f"({extra})" if extra else ""))
    if b.get("operating_margin") is not None:
        parts.append(f"영업이익률 {b['operating_margin']}%")
    return f"{head}: " + (", ".join(parts) or "값 없음")


def _flow(b: Mapping) -> str:
    big = lambda v: (("+" if v > 0 else "") + _big(v)) if v is not None else None  # 증감 지표 표기(get_metric)와 같이
    out = [
        _with("5일 순매수 외국인", big(b.get("foreign_net_buy_5d"))),
        _with("기관", big(b.get("inst_net_buy_5d"))),
        _with("개인", big(b.get("individual_net_buy_5d"))),
        _with("20일 순매수 시가총액 대비 외국인", _pct(b.get("foreign_net_buy_20d_pct_mcap"))),
        _with("기관", _pct(b.get("inst_net_buy_20d_pct_mcap"))),
    ]
    # 데이터 쪽 basis에는 metrics로 옮겨 뺀 공매도 설명도 있어서 쓰지 않는다
    text = _join(out)
    return f"{text}. 순매수는 최근 5거래일 합계, 시가총액 대비는 최근 20거래일 순매수 합계 ÷ 시가총액" if text else "값 없음"


def _sensitivities(b: Mapping) -> str:
    sure = [f"{f.get('factor')}({f.get('frequency')}) 편상관 {f.get('adjusted')}" for f in b.get("factors") or []
            if f.get("certain")]
    head = "뚜렷한 관계: " + ", ".join(sure) if sure else "뚜렷한 관계가 있는 요인 없음"
    caution = b.get("caution") or ""
    caution = " ".join(caution) if isinstance(caution, list) else caution  # 데이터 쪽은 문자열 목록(#120 리뷰)
    return f"{head}. 나머지 요인은 뚜렷한 관계가 없다. {caution}".strip()


_BLOCK_TEXT = {"target_price": _target_price, "financials": _financials, "disclosures": _disclosures,
               "macro": _macro, "index": _index, "sensitivities": _sensitivities,
               "valuation": _valuation_pos, "price_trend": _price_trend, "fundamental_trend": _fundamental_trend,
               "flow": _flow}
