"""온톨로지 입력값 계산 CLI. DB는 읽기만 하고, 결과는 CSV로 쓴다(DB에 저장하지 않음).

    python -m crawling.ontology_inputs sensitivities --as-of 2026-11-23 --level l1 --out sens_l1.csv
    python -m crawling.ontology_inputs sector-grades --as-of 2026-11-23 --out grades.csv
    python -m crawling.ontology_inputs macro-direction --as-of 2026-11-23 --out macro_direction.csv
    python -m crawling.ontology_inputs impacts --as-of 2026-11-23 --out impacts.csv
    python -m crawling.ontology_inputs kind --out kind_t1.csv [--kind-file corplist.html]
    python -m crawling.ontology_inputs issue-evidence --seed ../ontology/seed/ontology_seed.json --out evidence.csv
    python -m crawling.ontology_inputs monthly --out-dir ontology_inputs_out   # 매달 자동 계산 묶음

- sensitivities: 섹터(l1·l2) 또는 종목 × 요인의 원래 상관, 시장 효과 뺀 상관, 같은 부호 비율, 방향 확실 수.
  --seed를 주면 시드 SENSITIVE_TO 엣지의 가설·상태와 sign_check를 붙인다
- sector-grades: 섹터 금리(KTB_3Y_KR)·환율(USD_KRW) 등급 후보
- macro-direction: 지표가 오를 때 시장이 같이 움직였는지 (MACRO.direction 근거)
- impacts: 시드 IMPACTS 초안 관계의 데이터로 본 방향
- kind: KRX KIND 상장법인목록의 업종·주요제품으로 T1 세부 업종·지주사 후보 (파일을 안 주면 내려받음)
- issue-evidence: 시드 ISSUE마다 수혜·타격 종목 문서에서 근거 후보 조각 검색

결과는 온톨로지 쪽의 판단 재료다. 노출 여부·가설·확정 이름은 사람이 정한다.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg

from crawling.analytics import ontology_inputs as oi
from crawling.analytics.monthly_correlation import LEAD_MONTHS, WINDOW_MONTHS, monthly_log_changes
from crawling.config.clock import KST, today_kst
from crawling.db.postgres import connect

logger = logging.getLogger(__name__)

WINDOW_YEARS = 3  # 일별 민감도 적합 기간과 같게 (sim_loader)
DAILY_FACTORS = {"KTB_3Y_KR": "diff", "KTB_10Y_KR": "diff", "USD_KRW": "log"}
MONTHLY_FACTORS = ("BRENT", "CPI_KR", "DRAM_EXPORT_PRICE")
KIND_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"
# 시드 IMPACTS 초안 중 데이터가 있는 관계
EVENT_IMPACTS = [("BASE_RATE_KR", "KTB_3Y_KR"), ("BASE_RATE_KR", "KTB_10Y_KR"), ("BASE_RATE_KR", "USD_KRW")]
MONTHLY_IMPACTS = [("USD_KRW", "CPI_KR", 1), ("CPI_KR", "BASE_RATE_KR", 1), ("DRAM_EXPORT_PRICE", "KOSPI", 0)]


# ───────────────────────── 데이터 읽기 ─────────────────────────

def _as_of(connection: psycopg.Connection, day: date) -> date:
    row = connection.execute("select max(trade_date) from price_data where trade_date <= %s", (day,)).fetchone()
    if row[0] is None:
        raise SystemExit("price_data가 비어 있습니다")
    return row[0]


def _members(connection: psycopg.Connection, level: str) -> dict[str, list[str]]:
    """섹터 이름 → 핵심 종목. level이 ticker면 종목마다 자기 자신."""
    column = {"l1": "sector_l1", "l2": "sector_l2"}.get(level)
    rows = connection.execute(
        f"select ticker, {column or 'ticker'} from companies where is_core and {column or 'ticker'} is not null"
    ).fetchall()
    groups: dict[str, list[str]] = {}
    for ticker, group in rows:
        groups.setdefault(group, []).append(ticker)
    return groups


def _daily_frame(connection: psycopg.Connection, tickers: list[str], start: date, end: date):
    from crawling.sim_loader import _load_closes, _load_factors

    closes = _load_closes(connection, tickers, start, end)
    factors = _load_factors(connection, start, end)
    market = (np.log(factors["KOSPI"]).diff() * 100).rename("KOSPI")
    changes = {
        name: (factors[name].diff() if kind == "diff" else np.log(factors[name]).diff() * 100)
        for name, kind in DAILY_FACTORS.items() if name in factors
    }
    returns = {t: np.log(series).diff() * 100 for t, series in closes.items()}
    return returns, changes, market


def _monthly_frame(connection: psycopg.Connection, as_of: date):
    """종목 월 수익률, 지표 월 변화, 시장 대용(핵심 종목 동일가중 평균). as_of가 속한 달은 뺀다(끝나지 않음)."""
    month_end = date(as_of.year, as_of.month, 1)
    rows = connection.execute(
        "select p.ticker, p.month, p.close from price_monthly p join companies c using (ticker) "
        "where c.is_core and p.month < %s", (month_end,)
    ).fetchall()
    frame = pd.DataFrame(rows, columns=["ticker", "month", "close"])
    frame["month"] = pd.to_datetime(frame["month"])
    returns = {t: monthly_log_changes(g.set_index("month")["close"].astype(float)) for t, g in frame.groupby("ticker")}
    market = pd.DataFrame(returns).mean(axis=1).rename("market")
    return returns, market


def _macro_series(connection: psycopg.Connection, indicator: str, as_of: date, frequency: str | None = None) -> pd.Series:
    """as_of까지의 지표 값. 과거 기준일로 다시 돌려도 그 뒤 값이 섞이지 않게 한다(재현성).

    월별 지표는 날짜(그 달) 기준으로 자른다. 실제 공개일은 더 늦을 수 있다(공개 시차는 반영하지 않음).
    """
    query = "select date, value from macro_data where indicator_id = %s and date <= %s"
    params: list = [indicator, as_of]
    if frequency:
        query += " and frequency = %s"
        params.append(frequency)
    rows = connection.execute(query + " order by date", params).fetchall()
    series = pd.Series([float(v) for _, v in rows], index=pd.to_datetime([d for d, _ in rows]), dtype=float)
    return series[~series.index.duplicated(keep="last")]


def _monthly_change(series: pd.Series, how: str = "log") -> pd.Series:
    """일별 지표는 월평균으로 바꾼 뒤 변화. 월별 지표는 그대로 변화."""
    monthly = series.resample("MS").mean() if len(series) and (series.index.day != 1).any() else series
    if how == "diff":
        return monthly.diff().dropna()
    return monthly_log_changes(monthly)


# ───────────────────────── 명령 ─────────────────────────

# 계산 방식과 시장 대용. 저장 표(ontology_sensitivity_inputs)의 method 칸
METHOD = {"daily": "partial_corr_daily_kospi", "monthly": "partial_corr_monthly_core_equal_weight_lead1"}
FACTOR_FREQUENCY = [*[(f, "daily") for f in DAILY_FACTORS], *[(f, "monthly") for f in MONTHLY_FACTORS]]


def compute_sensitivities(connection, as_of: date, level: str) -> list[dict]:
    end, per_ticker = ticker_sensitivities(connection, as_of)
    return summarize(per_ticker, _members(connection, level), level, end)


def ticker_sensitivities(connection, as_of: date) -> tuple[date, dict[tuple[str, str], oi.TickerSensitivity]]:
    """핵심 종목 × 요인의 시장 효과 뺀 상관 (일별 3년, 월별 최대 120개월)."""
    end = _as_of(connection, as_of)
    tickers = sorted(t for members in _members(connection, "ticker").values() for t in members)
    returns, daily_changes, market = _daily_frame(connection, tickers, end - timedelta(days=365 * WINDOW_YEARS), end)
    m_returns, m_market = _monthly_frame(connection, end)

    monthly_changes = {}
    for factor in MONTHLY_FACTORS:
        change = monthly_log_changes(_macro_series(connection, factor, end, "monthly"))
        change.index = change.index - pd.DateOffset(months=LEAD_MONTHS)  # t+1월 변화를 t월 자리에
        monthly_changes[factor] = change

    per_ticker: dict[tuple[str, str], oi.TickerSensitivity] = {}
    for ticker in tickers:
        for factor, change in daily_changes.items():
            if ticker in returns:
                row = oi.ticker_sensitivity(ticker, factor, "daily", returns[ticker], change, market, oi.MIN_DAILY_OBS)
                if row:
                    per_ticker[(ticker, factor)] = row
        for factor, change in monthly_changes.items():
            if ticker not in m_returns:
                continue
            row = oi.ticker_sensitivity(ticker, factor, "monthly", m_returns[ticker], change, m_market,
                                        oi.MIN_MONTHLY_OBS, max_obs=WINDOW_MONTHS)
            if row:
                per_ticker[(ticker, factor)] = row

    return end, per_ticker


def summarize(per_ticker: dict, groups: dict[str, list[str]], level: str, end: date) -> list[dict]:
    """종목 값 → 섹터 요약(l1·l2) 또는 종목 행(ticker, 신뢰구간 포함)."""
    out = []
    for group, members in sorted(groups.items()):
        for factor, frequency in FACTOR_FREQUENCY:
            rows = [per_ticker[(t, factor)] for t in members if (t, factor) in per_ticker]
            if not rows:
                continue
            base = {"level": level, "group": group, "factor": factor, "frequency": frequency, "as_of": end.isoformat(),
                    "method": METHOD[frequency]}
            if level == "ticker":
                r = rows[0]
                out.append({**base, **oi._window(rows), "n_obs": r.n, "raw": round(r.raw, 4), "adjusted": round(r.adjusted, 4),
                            "ci_low": round(r.ci_low, 4), "ci_high": round(r.ci_high, 4), "certain": r.certain,
                            "p_value": oi.correlation_p_value(r.adjusted, r.n, n_controls=1)})
            else:
                out.append({**base, **oi.sector_summary(rows)})
    if level == "ticker":
        add_q_values(out)
    return out


def add_q_values(rows: list[dict]) -> None:
    """종목 행의 p값을 지표(factor)별로 BH 보정해 q_value를 붙인다."""
    by_factor: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("p_value") is not None:
            by_factor.setdefault(row["factor"], []).append(row)
    for group in by_factor.values():
        for row, q in zip(group, oi.bh_q_values([r["p_value"] for r in group])):
            row["q_value"] = round(q, 4)
    for row in rows:
        row["p_value"] = None if row.get("p_value") is None else round(row["p_value"], 6)
        row.setdefault("q_value", None)


TABLE = "ontology_sensitivity_inputs"
TABLE_KEY = ("as_of", "level", "group_id", "factor")
_TICKER_COLUMNS = ("n_obs", "raw", "adjusted", "ci_low", "ci_high", "certain", "p_value", "q_value")
_SECTOR_COLUMNS = {"n_tickers": "n_tickers", "raw_median": "raw_median", "adjusted_median": "adjusted_median",
                   "same_sign": "same_sign", "same_sign_ratio": "same_sign_ratio", "certain": "n_certain",
                   "certain_pos": "n_certain_pos", "certain_neg": "n_certain_neg", "n_obs_min": "n_obs_min",
                   "n_obs_max": "n_obs_max"}


def table_rows(rows: list[dict]) -> list[dict]:
    """summarize 결과 → ontology_sensitivity_inputs 행. 모든 행이 같은 칸을 갖게 하고, 없는 칸은 None."""
    out = []
    for row in rows:
        record = {"as_of": row["as_of"], "level": row["level"], "group_id": row["group"], "factor": row["factor"],
                  "frequency": row["frequency"], "method": row["method"], "window_start": row["window_start"],
                  "window_end": row["window_end"]}
        record.update({c: None for c in (*_TICKER_COLUMNS, *_SECTOR_COLUMNS.values())})
        if row["level"] == "ticker":
            record.update({c: row.get(c) for c in _TICKER_COLUMNS})
        else:
            record.update({dst: row.get(src) for src, dst in _SECTOR_COLUMNS.items()})
        out.append(record)
    return out


def save_sensitivities(connection, rows: list[dict]) -> int:
    """기준일별로 쌓는다. 같은 기준일을 다시 저장하면 그 기준일 행을 모두 지우고 새로 넣는다(한 트랜잭션).

    다시 계산할 때 표본이 모자라 빠진 종목·지표의 예전 행이 남지 않게 하고, computed_at은 저장한 시각(KST)으로 바뀐다.
    """
    from crawling.db.postgres import upsert

    records = table_rows(rows)
    if not records:
        return 0
    computed_at = datetime.now(KST)
    for record in records:
        record["computed_at"] = computed_at
    as_ofs = sorted({date.fromisoformat(r["as_of"]) for r in records})
    with connection.transaction():
        connection.execute(f"delete from {TABLE} where as_of = any(%s)", (as_ofs,))
        return upsert(connection, TABLE, records, key_columns=list(TABLE_KEY))


def compute_monthly(connection, as_of: date, out_dir: Path, seed: Path | None, save: bool = False) -> list[Path]:
    """매달 자동 계산: 민감도(종목·l1·l2)·섹터 등급·매크로 방향·IMPACTS를 한 번에 out_dir/<기준일>/에 쓴다.

    save면 민감도(종목·l1·l2)를 ontology_sensitivity_inputs에도 저장한다. 나머지 결과는 CSV만 쓴다.
    """
    end, per_ticker = ticker_sensitivities(connection, as_of)
    folder = out_dir / end.isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    results = {}
    for level in ("ticker", "l1", "l2"):
        rows = summarize(per_ticker, _members(connection, level), level, end)
        results[f"sensitivities_{level}"] = attach_seed(rows, seed) if seed and level == "l1" else rows
    results["sector_grades"] = sector_grades(results["sensitivities_l1"], 0.10, 0.05, 0.05)
    results["macro_direction"] = compute_macro_direction(connection, end)
    results["impacts"] = compute_impacts(connection, end)
    paths = []
    for name, rows in results.items():
        path = folder / f"{name}.csv"
        write_csv(rows, path)
        paths.append(path)
    if save:
        saved = save_sensitivities(connection, [r for lv in ("ticker", "l1", "l2") for r in results[f"sensitivities_{lv}"]])
        logger.info("%s에 %s행 저장 (as_of %s)", TABLE, saved, end)
    return paths


def attach_seed(rows: list[dict], seed_path: Path) -> list[dict]:
    """시드 SENSITIVE_TO 엣지(섹터 → 지표)의 가설·상태를 붙이고 시장 효과 기준 sign_check를 계산한다."""
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    names = {s["sector_id"]: s.get("wics_name") or s["name"] for s in seed["nodes"]["sectors"]}
    edges = {(names.get(e["src"]), e["dst"]): e for e in seed["edges"]["sensitive_to"]}
    for row in rows:
        edge = edges.get((row["group"], row["factor"]))
        row["seed_status"] = edge["status"] if edge else ""
        row["expected_sign"] = edge.get("expected_sign", "") if edge else ""
        row["sign_check_adjusted"] = oi.sign_check(row["adjusted_median"], row["expected_sign"]) if edge else ""
        row["passes_rule"] = oi.passes_exposure_rule(row)
    return rows


def compute_sector_grades(connection, as_of: date, high: float, medium: float, neutral: float) -> list[dict]:
    return sector_grades(compute_sensitivities(connection, as_of, "l1"), high, medium, neutral)


def sector_grades(l1_rows: list[dict], high: float, medium: float, neutral: float) -> list[dict]:
    rows = {(r["group"], r["factor"]): r for r in l1_rows}
    out = []
    for group in sorted({g for g, _ in rows}):
        rate, fx = rows.get((group, "KTB_3Y_KR")), rows.get((group, "USD_KRW"))
        out.append({
            "sector": group,
            "rate_sensitivity": oi.rate_grade(rate["adjusted_median"], high, medium) if rate else "",
            "rate_value": rate["adjusted_median"] if rate else "",
            "rate_certain": f'{rate["certain"]}/{rate["n_tickers"]}' if rate else "",
            "fx_sensitivity": oi.fx_grade(fx["adjusted_median"], neutral) if fx else "",
            "fx_value": fx["adjusted_median"] if fx else "",
            "fx_certain": f'{fx["certain"]}/{fx["n_tickers"]}' if fx else "",
            "as_of": rate["as_of"] if rate else "",
        })
    return out


def compute_macro_direction(connection, as_of: date) -> list[dict]:
    end = _as_of(connection, as_of)
    start = end - timedelta(days=365 * WINDOW_YEARS)
    _, daily_changes, market = _daily_frame(connection, [], start, end)
    out = []
    for name, change in daily_changes.items():
        result = oi.macro_direction(change, market, oi.MIN_DAILY_OBS)
        if result:
            out.append({"indicator": name, "frequency": "daily", "window": f"{start}~{end}", **result})
    _, m_market = _monthly_frame(connection, end)
    for name in MONTHLY_FACTORS:
        change = monthly_log_changes(_macro_series(connection, name, end, "monthly")).tail(WINDOW_MONTHS)
        result = oi.macro_direction(change, m_market, oi.MIN_MONTHLY_OBS)
        if result:
            out.append({"indicator": name, "frequency": "monthly", "window": f"최근 {WINDOW_MONTHS}개월",
                        "market": "핵심 종목 동일가중 평균", **result})
    base = _macro_series(connection, "BASE_RATE_KR", end)
    events = [e for e in oi.step_events(base) if e[0].date() >= start]
    kospi_level = _kospi_level(connection, start, end)
    response = oi.event_response(events, np.log(kospi_level) * 100)
    if response:
        out.append({"indicator": "BASE_RATE_KR", "frequency": "event", "window": f"{start}~{end}",
                    "direction": {"same": "up_positive", "opposite": "up_negative"}.get(response["direction"], "mixed"),
                    **{f"event_{k}": v for k, v in response.items()}})
    return out


def _kospi_level(connection, start: date, end: date) -> pd.Series:
    rows = connection.execute(
        "select trade_date, close from index_daily where index_code = '1001' and trade_date between %s and %s order by 1",
        (start, end),
    ).fetchall()
    return pd.Series([float(c) for _, c in rows], index=pd.to_datetime([d for d, _ in rows]))


def compute_impacts(connection, as_of: date) -> list[dict]:
    end = _as_of(connection, as_of)
    out = []
    base = _macro_series(connection, "BASE_RATE_KR", end)
    events = oi.step_events(base)
    for src, dst in EVENT_IMPACTS:
        target = _macro_series(connection, dst, end)
        result = oi.event_response(events, target if dst != "USD_KRW" else np.log(target) * 100)
        if result:
            out.append({"src": src, "dst": dst, "method": "event_-1d_+5d", "window": f"{events[0][0].date()}~{end}",
                        **result})
    _, m_market = _monthly_frame(connection, end)
    for src, dst, lead in MONTHLY_IMPACTS:
        x = _monthly_change(_macro_series(connection, src, end), "diff" if src == "BASE_RATE_KR" else "log")
        y = m_market if dst == "KOSPI" else _monthly_change(_macro_series(connection, dst, end),
                                                             "diff" if dst == "BASE_RATE_KR" else "log")
        result = oi.lead_correlation(x.tail(WINDOW_MONTHS * 2), y, lead, oi.MIN_MONTHLY_OBS)
        if result:
            direction = "unclear" if not result["certain"] else ("same" if result["corr"] > 0 else "opposite")
            out.append({"src": src, "dst": dst, "method": f"monthly_corr_lead{lead}", "direction": direction,
                        **result})
    return out


def compute_kind(connection, kind_file: Path | None, seed: Path | None = None) -> list[dict]:
    if kind_file:
        raw = kind_file.read_bytes()
    else:
        import httpx

        raw = httpx.get(KIND_URL, timeout=60, headers={"User-Agent": "Mozilla/5.0"}).content
    rows = {r.get("종목코드", ""): r for r in oi.parse_kind_corp_list(raw.decode("euc-kr", errors="replace"))}
    core = connection.execute(
        "select ticker, name, sector_l1, sector_l2 from companies where is_core order by ticker"
    ).fetchall()
    seeded = {}
    if seed:
        data = json.loads(seed.read_text(encoding="utf-8"))
        nodes = data["nodes"].get("companies_t1") or data["nodes"].get("companies") or []
        seeded = {c["ticker"]: c for c in nodes}
    out = []
    for ticker, name, l1, l2 in core:
        kind = rows.get(ticker, {})
        industry, product = kind.get("업종", ""), kind.get("주요제품", "")
        label, rule = oi.sub_industry_candidate(industry, product)
        holding, holding_reason = oi.holding_candidate(name, industry, product)
        out.append({"ticker": ticker, "name": name, "sector_l1": l1, "sector_l2": l2, "kind_industry": industry,
                    "kind_product": product, "sub_industry_candidate": label or "", "rule": rule or "",
                    "is_holding_candidate": holding, "holding_reason": holding_reason or "",
                    "in_kind": bool(kind)})
        if seed:
            node = seeded.get(ticker, {})
            seed_sub = node.get("sub_industry") or ""
            out[-1].update({
                "seed_sub_industry": seed_sub, "seed_sub_industry_source": node.get("sub_industry_source") or "",
                "sub_industry_differs": bool(label or seed_sub) and (label or "") != seed_sub,
                "seed_is_holding": node.get("is_holding"), "seed_holding_type": node.get("holding_type") or "",
                "holding_differs": node.get("is_holding") is not None and bool(node.get("is_holding")) != holding,
            })
    return out


def compute_issue_evidence(seed_path: Path, top_k: int, per_issue: int, as_of: str | None) -> list[dict]:
    """시드 ISSUE마다 BENEFITS/HURTS로 연결된 종목 문서에서 이슈 이름으로 검색한 근거 후보."""
    from processing.functions.search_documents import search_documents

    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    targets: dict[str, list[str]] = {}
    for edge in seed["edges"]["benefits_hurts"]:
        if edge["dst_type"] == "COMPANY":
            targets.setdefault(edge["src"], []).append(edge["dst"])
    out = []
    for issue in seed["nodes"]["issues"]:
        found: dict[str, dict] = {}
        for ticker in dict.fromkeys(targets.get(issue["issue_id"], [])):
            result = search_documents(issue["name"], ticker, top_k=top_k, as_of=as_of)
            for hit in result.get("results", []):
                current = found.get(hit["chunk_id"])
                if current is None or hit.get("score", 0) > current["score"]:
                    found[hit["chunk_id"]] = {
                        "issue_id": issue["issue_id"], "issue_name": issue["name"], "ticker": ticker,
                        "chunk_id": hit["chunk_id"], "document_type": hit.get("document_type", ""),
                        "date": hit.get("date", ""), "author_org": hit.get("author_org", ""),
                        "title": hit.get("title", ""), "score": hit.get("score", 0), "mode": result.get("mode", ""),
                    }
        ranked = sorted(found.values(), key=lambda r: r["score"], reverse=True)[:per_issue]
        if not ranked:
            out.append({"issue_id": issue["issue_id"], "issue_name": issue["name"], "ticker": "", "chunk_id": "",
                        "document_type": "", "date": "", "author_org": "", "title": "(근거 후보 없음)", "score": 0,
                        "mode": ""})
        out.extend(ranked)
    return out


# ───────────────────────── CLI ─────────────────────────

def write_csv(rows: list[dict], path: Path | None) -> None:
    if not rows:
        logger.warning("결과가 없습니다")
        return
    columns = list(dict.fromkeys(k for row in rows for k in row))
    handle = open(path, "w", newline="", encoding="utf-8-sig") if path else sys.stdout
    try:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    finally:
        if path:
            handle.close()
    logger.info("%s행 → %s", len(rows), path or "stdout")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="온톨로지 입력값 계산 (DB 읽기 전용, CSV 출력)")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("sensitivities", "sector-grades", "macro-direction", "impacts", "kind", "issue-evidence", "monthly"):
        p = sub.add_parser(name)
        p.add_argument("--out", type=Path, default=None, help="CSV 경로 (없으면 화면)")
        p.add_argument("--as-of", type=date.fromisoformat, default=None, help="기준일 (기본 오늘 KST)")
        if name == "sensitivities":
            p.add_argument("--level", choices=("l1", "l2", "ticker"), default="l1")
            p.add_argument("--seed", type=Path, default=None, help="온톨로지 시드 JSON (가설·상태·sign_check 붙임)")
        if name == "sector-grades":
            p.add_argument("--high", type=float, default=0.10)
            p.add_argument("--medium", type=float, default=0.05)
            p.add_argument("--neutral", type=float, default=0.05)
        if name == "kind":
            p.add_argument("--kind-file", type=Path, default=None, help="미리 받은 KIND 목록 파일 (없으면 내려받음)")
            p.add_argument("--seed", type=Path, default=None, help="온톨로지 시드 JSON (확정값과 차이를 같이 냄)")
        if name == "monthly":
            p.add_argument("--out-dir", type=Path, default=Path("ontology_inputs_out"), help="기준일 폴더를 만들 위치")
            p.add_argument("--seed", type=Path, default=None, help="온톨로지 시드 JSON (섹터 민감도에 가설·상태 붙임)")
            p.add_argument("--save", action="store_true",
                           help=f"민감도(종목·l1·l2)를 {TABLE} 표에 저장 (이 옵션만 DB에 씀)")
        if name == "issue-evidence":
            p.add_argument("--seed", type=Path, required=True)
            p.add_argument("--top-k", type=int, default=3, help="종목마다 검색할 조각 수")
            p.add_argument("--per-issue", type=int, default=5, help="이슈마다 남길 후보 수")
    return parser.parse_args(argv)


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    args = parse_args(argv)
    as_of = args.as_of or today_kst()
    if args.command == "issue-evidence":
        write_csv(compute_issue_evidence(args.seed, args.top_k, args.per_issue, args.as_of and args.as_of.isoformat()),
                  args.out)
        return
    with connect() as connection:
        if not (args.command == "monthly" and args.save):
            connection.execute("set session characteristics as transaction read only")
        if args.command == "monthly":
            compute_monthly(connection, as_of, args.out_dir, args.seed, save=args.save)
            return
        if args.command == "sensitivities":
            rows = compute_sensitivities(connection, as_of, args.level)
            if args.seed:
                rows = attach_seed(rows, args.seed)
        elif args.command == "sector-grades":
            rows = compute_sector_grades(connection, as_of, args.high, args.medium, args.neutral)
        elif args.command == "macro-direction":
            rows = compute_macro_direction(connection, as_of)
        elif args.command == "impacts":
            rows = compute_impacts(connection, as_of)
        else:
            rows = compute_kind(connection, args.kind_file, args.seed)
    write_csv(rows, args.out)


if __name__ == "__main__":
    main()
