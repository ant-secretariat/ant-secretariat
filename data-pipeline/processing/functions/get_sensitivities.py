"""종목의 시장 효과를 뺀 매크로 민감도 (ontology_sensitivity_inputs, #67).

토론 macro 아젠다의 민감도 블록이 쓴다(#84 Q4-1, 데이터 에이전트 기획서 4-2절).
원래 상관(raw)은 주지 않는다. 시장 전체 움직임이 섞인 관계라 ADR 0011이 노출하지 않기로 했기 때문이다.
엣지 노출 여부는 온톨로지(get_ontology_context)가 따로 판단한다.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from crawling.config.clock import today_kst

logger = logging.getLogger(__name__)

CAUTION = [
    "시장 효과(코스피)를 양쪽에서 뺀 상관(편상관)이고 인과가 아님",
    "월별 값은 t월 주가와 t+1월 지표 변화의 상관(주가가 다음 달 지표를 먼저 반영하는 경향)",
    "certain=false면 95% 신뢰구간이 0을 포함해 방향이 불확실",
]
COLUMNS = ("factor", "frequency", "method", "window_start", "window_end", "n_obs", "adjusted", "ci_low", "ci_high",
           "certain", "q_value", "as_of")


def get_sensitivities(ticker: str, as_of: Optional[str] = None) -> dict:
    """as_of 이전 가장 최근 계산 기준일의 종목 민감도(시장 효과를 뺀 값만).

    - factors: 요인마다 frequency(daily·monthly), adjusted(편상관), ci_low·ci_high(Fisher 95%), certain, q_value
      (지표별 전체 종목 Benjamini-Hochberg), n_obs, window_start·window_end. 일별 먼저, 그 안에서 요인 이름 순
    - as_of는 계산 기준일(매달 다시 계산, monthly --save). 그날 이전에 계산된 값이 없으면 factors는 빈 목록,
      reason="no_data"(미래에 계산한 값을 과거 기준일에 쓰지 않음)
    - 조회에 실패하면 factors는 null, error="sensitivities_unavailable"
    """
    ticker = (ticker or "").strip()
    requested = date.fromisoformat(as_of).isoformat() if as_of else today_kst().isoformat()  # 형식이 틀리면 ValueError
    base = {"ticker": ticker, "requested_as_of": requested, "caution": CAUTION}

    # 접속 주소가 메시지에 섞일 수 있어 종류만 남긴다
    try:
        from crawling.db.postgres import connect

        with connect() as connection:
            rows = connection.execute(
                f"""
                select {", ".join(COLUMNS)} from ontology_sensitivity_inputs
                where level = 'ticker' and group_id = %(ticker)s
                  and as_of = (select max(as_of) from ontology_sensitivity_inputs
                               where level = 'ticker' and group_id = %(ticker)s and as_of <= %(as_of)s::date)
                order by frequency, factor
                """,
                {"ticker": ticker, "as_of": requested},
            ).fetchall()
    except Exception as exc:
        logger.error("민감도 조회 실패: %s(%s)", ticker, type(exc).__name__)
        return {**base, "as_of": None, "factors": None, "error": "sensitivities_unavailable"}

    if not rows:
        return {**base, "as_of": None, "factors": [], "reason": "no_data"}
    factors = [_factor(dict(zip(COLUMNS, row))) for row in rows]
    return {**base, "as_of": rows[0][COLUMNS.index("as_of")].isoformat(), "factors": factors, "reason": None}


def _factor(row: dict) -> dict:
    return {
        "factor": row["factor"],
        "frequency": row["frequency"],
        "method": row["method"],
        "adjusted": _round(row["adjusted"]),
        "ci_low": _round(row["ci_low"]),
        "ci_high": _round(row["ci_high"]),
        "certain": row["certain"],
        "q_value": _round(row["q_value"]),
        "n_obs": row["n_obs"],
        "window_start": row["window_start"].isoformat(),
        "window_end": row["window_end"].isoformat(),
    }


def _round(value):
    return round(float(value), 4) if value is not None else None
