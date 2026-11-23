"""온톨로지 입력값 계산 (DB를 읽지 않는 순수 함수).

온톨로지 시드의 데이터 칸을 손으로 옮기지 않고 같은 방식으로 다시 계산하기 위한 함수들이다.
DB 조회·파일 입출력은 crawling/ontology_inputs.py가 맡는다. 결과는 판단 재료이고, 노출 여부·가설은
온톨로지 쪽이 정한다.

- 시장 효과를 뺀 상관(편상관): 종목 수익률과 요인 변화에서 각각 시장 수익률 효과를 뺀 잔차끼리의 상관.
  섹터 중앙값으로 묶으면 SENSITIVE_TO 후보값이 된다 (#29·#56 검증 방식)
- 섹터 금리·환율 등급: 위 값의 섹터 중앙값 크기·부호로 나눈다. 기준값은 인자로 받는다
- 매크로 방향: 지표 변화와 시장 수익률의 상관 부호 (같이 움직인 것이지 원인은 아님)
- 기준금리 사건 분석: 기준금리가 바뀐 날 전후 다른 지표의 변화 방향
- KIND 상장법인목록: 업종·주요제품으로 세부 업종·지주사 후보
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from statistics import median

import numpy as np
import pandas as pd

Z_95 = 1.959964
MIN_DAILY_OBS = 250
MIN_MONTHLY_OBS = 24


# ───────────────────────── 시장 효과를 뺀 상관 ─────────────────────────

def residual(y: np.ndarray, controls: np.ndarray) -> np.ndarray:
    """controls(열 여러 개)로 y를 최소제곱 회귀한 잔차. 상수항을 포함한다."""
    x = np.column_stack([np.ones(len(y)), controls])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    return y - x @ coef


def partial_correlation(y, f, controls) -> float:
    """controls 효과를 y와 f 양쪽에서 뺀 뒤의 상관."""
    y, f = np.asarray(y, dtype=float), np.asarray(f, dtype=float)
    c = np.asarray(controls, dtype=float).reshape(len(y), -1)
    return float(np.corrcoef(residual(y, c), residual(f, c))[0, 1])


def correlation_ci(r: float, n: int, n_controls: int = 0) -> tuple[float | None, float | None]:
    """Fisher 변환 95% 신뢰구간. 표본이 너무 적으면 (None, None)."""
    dof = n - n_controls - 3
    if dof <= 0 or not math.isfinite(r):
        return None, None
    z = math.atanh(max(min(r, 0.999999), -0.999999))
    half = Z_95 / math.sqrt(dof)
    return math.tanh(z - half), math.tanh(z + half)


def is_certain(low: float | None, high: float | None) -> bool:
    """신뢰구간이 0을 포함하지 않으면 방향이 확실하다."""
    return low is not None and high is not None and (low > 0 or high < 0)


@dataclass(frozen=True)
class TickerSensitivity:
    ticker: str
    factor: str
    frequency: str  # daily / monthly
    n: int
    raw: float
    adjusted: float
    ci_low: float | None
    ci_high: float | None

    @property
    def certain(self) -> bool:
        return is_certain(self.ci_low, self.ci_high)


def ticker_sensitivity(ticker: str, factor: str, frequency: str, stock: pd.Series, factor_change: pd.Series,
                       market: pd.Series, min_obs: int, max_obs: int | None = None) -> TickerSensitivity | None:
    """같은 날짜(달)에 세 값이 모두 있는 행만 쓴다. max_obs가 있으면 최근 그만큼만. 행이 min_obs보다 적으면 None."""
    frame = pd.concat([stock.rename("y"), factor_change.rename("f"), market.rename("m")], axis=1, join="inner").dropna()
    if max_obs:
        frame = frame.tail(max_obs)
    if len(frame) < min_obs or frame["y"].std() == 0 or frame["f"].std() == 0:
        return None
    raw = float(frame["y"].corr(frame["f"]))
    adjusted = partial_correlation(frame["y"].values, frame["f"].values, frame[["m"]].values)
    low, high = correlation_ci(adjusted, len(frame), n_controls=1)
    return TickerSensitivity(ticker, factor, frequency, len(frame), raw, adjusted, low, high)


def sign(x: float) -> int:
    return (x > 0) - (x < 0)


def sector_summary(rows: list[TickerSensitivity]) -> dict:
    """섹터 소속 종목 값 → 섹터 후보값. 같은 부호 비율은 시장 효과 뺀 중앙값 기준이다."""
    raw_median = median(r.raw for r in rows)
    adjusted_median = median(r.adjusted for r in rows)
    direction = sign(adjusted_median)
    certain = [r for r in rows if r.certain]
    return {
        "n_tickers": len(rows),
        "raw_median": round(raw_median, 4),
        "adjusted_median": round(adjusted_median, 4),
        "same_sign": sum(1 for r in rows if sign(r.adjusted) == direction),
        "same_sign_ratio": round(sum(1 for r in rows if sign(r.adjusted) == direction) / len(rows), 3),
        "certain": len(certain),
        "certain_pos": sum(1 for r in certain if r.adjusted > 0),
        "certain_neg": sum(1 for r in certain if r.adjusted < 0),
        "n_obs_min": min(r.n for r in rows),
        "n_obs_max": max(r.n for r in rows),
    }


def passes_exposure_rule(summary: dict, min_ratio: float = 0.7, min_tickers: int = 3) -> bool:
    """#29의 임시 기준: 같은 부호 70% 이상, 방향 확실 종목이 과반, 3종목 이상."""
    n = summary["n_tickers"]
    return n >= min_tickers and summary["same_sign_ratio"] >= min_ratio and summary["certain"] * 2 > n


def sign_check(value: float, expected: str, near_zero: float = 0.05) -> str:
    """가설 부호(+, -, ±)와 비교. 절댓값이 near_zero보다 작으면 near_zero."""
    if abs(value) < near_zero:
        return "near_zero"
    if expected not in ("+", "-"):
        return "no_hypothesis"
    return "match" if (value > 0) == (expected == "+") else "mismatch"


# ───────────────────────── 섹터 등급 ─────────────────────────

def rate_grade(value: float, high: float = 0.10, medium: float = 0.05) -> str:
    """금리 민감도 등급: 시장 효과 뺀 섹터 중앙값의 절댓값."""
    size = abs(value)
    return "high" if size >= high else "medium" if size >= medium else "low"


def fx_grade(value: float, neutral: float = 0.05) -> str:
    """환율 민감도: 원/달러가 오를 때 같이 오르면 positive, 내리면 negative, 0 근처면 neutral."""
    if abs(value) < neutral:
        return "neutral"
    return "positive" if value > 0 else "negative"


# ───────────────────────── 매크로 방향 ─────────────────────────

def macro_direction(indicator_change: pd.Series, market: pd.Series, min_obs: int, neutral: float = 0.05) -> dict | None:
    """지표 변화와 같은 기간 시장 수익률의 상관 → up_positive / up_negative / mixed."""
    frame = pd.concat([indicator_change.rename("x"), market.rename("m")], axis=1, join="inner").dropna()
    if len(frame) < min_obs or frame["x"].std() == 0:
        return None
    r = float(frame["x"].corr(frame["m"]))
    low, high = correlation_ci(r, len(frame))
    label = "mixed" if abs(r) < neutral or not is_certain(low, high) else ("up_positive" if r > 0 else "up_negative")
    return {"corr": round(r, 4), "ci_low": round(low, 4), "ci_high": round(high, 4), "n": len(frame), "direction": label}


def lead_correlation(x: pd.Series, y: pd.Series, lead: int, min_obs: int) -> dict | None:
    """x(t)와 y(t+lead)의 상관. 월 인덱스(MS)를 가정한다."""
    shifted = y.copy()
    shifted.index = shifted.index - pd.DateOffset(months=lead)
    frame = pd.concat([x.rename("x"), shifted.rename("y")], axis=1, join="inner").dropna()
    if len(frame) < min_obs or frame["x"].std() == 0 or frame["y"].std() == 0:
        return None
    r = float(frame["x"].corr(frame["y"]))
    low, high = correlation_ci(r, len(frame))
    return {"corr": round(r, 4), "ci_low": round(low, 4), "ci_high": round(high, 4), "n": len(frame),
            "certain": is_certain(low, high)}


def step_events(levels: pd.Series) -> list[tuple[pd.Timestamp, float]]:
    """계단식 지표(기준금리)가 바뀐 날과 변화폭."""
    levels = levels.dropna().sort_index()
    change = levels.diff()
    return [(day, float(delta)) for day, delta in change.items() if pd.notna(delta) and delta != 0]


def event_response(events: list[tuple[pd.Timestamp, float]], target: pd.Series, before: int = 1,
                   after: int = 5, majority: float = 0.65) -> dict | None:
    """사건일 before 거래일 전 → after 거래일 뒤 target 변화가 사건 방향과 같은 비율.

    같은 방향(또는 반대 방향)이 majority 이상일 때만 same·opposite, 아니면 unclear.
    """
    target = target.dropna().sort_index()
    index = target.index
    same, opposite, moves = 0, 0, []
    for day, delta in events:
        pos = index.searchsorted(day)
        start, end = pos - before, pos + after
        if start < 0 or end >= len(index):
            continue
        move = float(target.iloc[end] - target.iloc[start])
        moves.append(move * sign(delta))
        if move == 0:
            continue
        if sign(move) == sign(delta):
            same += 1
        else:
            opposite += 1
    if not moves:
        return None
    counted = same + opposite
    share = same / counted if counted else 0.5
    return {
        "events": len(moves), "same": same, "opposite": opposite, "same_ratio": round(share, 3),
        "direction": "same" if share >= majority else "opposite" if share <= 1 - majority else "unclear",
        "mean_move_signed": round(sum(moves) / len(moves), 4),
    }


# ───────────────────────── KIND 상장법인목록 ─────────────────────────

# 업종·주요제품 → 짧은 세부 업종 이름. 위에서부터 처음 맞는 규칙을 쓴다(후보일 뿐, 확정은 사람)
SUB_INDUSTRY_RULES: list[tuple[str, str, str]] = [
    # (보는 칸: industry / product, 정규식, 짧은 이름)
    ("industry", r"절연선|케이블", "전선"),
    ("product", r"변압기|차단기|배전반|전력기기", "전력기기"),
    ("industry", r"전동기|발전기|전기 변환", "전력기기"),
    ("industry", r"일차전지|이차전지|축전지", "2차전지"),
    ("product", r"양극재|음극재|전구체", "2차전지 소재"),
    ("industry", r"선박|보트 건조", "조선"),
    ("industry", r"항공기|우주선", "방산·항공"),
    ("product", r"방산|무기|탄약|유도무기", "방산"),
    ("product", r"원자로|원전|터빈|터어빈", "발전설비"),
    ("industry", r"인쇄회로기판|전자부품", "전자부품·PCB"),
    ("product", r"P\.?C\.?B|인쇄회로기판", "전자부품·PCB"),
    ("industry", r"반도체 제조용 기계|특수 목적용 기계", "반도체 장비"),
    ("product", r"반도체.*장비|후공정장비", "반도체 장비"),
    ("industry", r"해상 운송", "해운"),
    ("industry", r"항공 여객|항공 운송", "항공운송"),
    ("industry", r"화물|물류|운송관련", "물류"),
    ("industry", r"화장품", "화장품"),
    ("industry", r"석유 정제", "정유"),
]
HOLDING_NAME = re.compile(r"지주|홀딩스")
HOLDING_INDUSTRY = "기타 금융업"


def parse_kind_corp_list(html_text: str) -> list[dict]:
    """KIND 상장법인목록 다운로드(HTML 표) → 행 목록. 칸 이름은 첫 줄을 그대로 쓴다."""
    import html as html_lib

    def cells(row: str) -> list[str]:
        return [html_lib.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", row, re.S)]

    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S)
    if not rows:
        return []
    header = cells(rows[0])
    return [dict(zip(header, cells(row))) for row in rows[1:] if cells(row)]


def sub_industry_candidate(industry: str, product: str) -> tuple[str | None, str | None]:
    """(짧은 이름 후보, 맞은 규칙). 규칙에 없으면 (None, None)."""
    fields = {"industry": industry or "", "product": product or ""}
    for field, pattern, label in SUB_INDUSTRY_RULES:
        if re.search(pattern, fields[field]):
            return label, f"{field}:{pattern}"
    return None, None


def holding_candidate(name: str, industry: str, product: str) -> tuple[bool, str | None]:
    """지주사 후보와 근거. 이름에 지주·홀딩스가 있거나, 업종이 기타 금융업이면서 주요제품에 지주가 있으면."""
    if HOLDING_NAME.search(name or ""):
        return True, "name"
    if (industry or "") == HOLDING_INDUSTRY and "지주" in (product or ""):
        return True, "kind_industry_product"
    return False, None
