"""관문1 결과 → precheck 입력 어댑터.

오케스트레이터 관문1(`resolve_company`)이 이미 받아 온 `tier`·`data_status`를 precheck가 쓰는 모양으로
바꾼다. `get_available_data_status`는 종목당 약 0.3초라 precheck 안에서 다시 부르지 않는다(수경 #32 제안,
오케스트레이터 기획서 #68 리뷰).

조회 실패는 "데이터 없음"으로 바꾸지 않는다(헌법 원칙 III). 아래 경우는 모두 `None`을 돌려주고,
precheck가 `DataStatusUnavailable`을 던진다. 오케스트레이터는 이를 503 `upstream_unavailable`로 바꾼다.

- `data_status`가 없음(`resolve_company`가 예외를 잡아 `None`을 넣은 경우)
- `data_status.error`가 있음(#53: `"data_status_unavailable"`)
- `tier`가 없거나 알 수 없는 값
- precheck 설정이 쓰는 소스 키가 `sources`에 없거나 `count`가 null

    resolved = {t: resolve_company(t) for t in tickers}          # 관문1
    companies = [company_context(resolved[t]) for t in tickers]
    result = precheck(query, companies, data_status=data_status_provider(resolved),
                      company_mentioned=mentioned)
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Mapping, Optional

from agents.debate_renewal.contracts import CompanyContext, Tier
from agents.debate_renewal.precheck.config import PrecheckConfig, load_default_config
from agents.debate_renewal.precheck.engine import (
    KST,
    DataStatusProvider,
    SourceStatus,
    TickerDataStatus,
)

logger = logging.getLogger(__name__)


def required_source_keys(config: PrecheckConfig | None = None) -> frozenset[str]:
    """precheck 설정(intent_data_sources.json)의 requires_any에 나오는 소스 키 전부."""
    cfg = config or load_default_config()
    return frozenset(key for src in cfg.sources.values() for key in src.requires_any)


def company_context(resolved: Mapping[str, Any]) -> CompanyContext:
    """`resolve_company`의 exact 결과 → `CompanyContext`. exact가 아니면 관문1에서 이미 거절했어야 한다."""
    if resolved.get("status") != "exact":
        raise ValueError(f"관문1에서 확정되지 않은 종목: status={resolved.get('status')!r}")
    tier = _tier(resolved.get("tier"))
    if tier is None:
        raise ValueError(f"종목 등급(tier)을 알 수 없음: {resolved.get('ticker')!r}")
    return CompanyContext(
        ticker=resolved["ticker"],
        company=resolved.get("company") or "",
        sector=resolved.get("sector") or "",
        tier=tier,
    )


def ticker_data_status(resolved: Mapping[str, Any], config: PrecheckConfig | None = None) -> Optional[TickerDataStatus]:
    """`resolve_company` 결과 하나 → `TickerDataStatus`. 상태를 믿을 수 없으면 `None`."""
    ticker = resolved.get("ticker")
    tier = _tier(resolved.get("tier"))
    status = resolved.get("data_status")
    if tier is None:
        logger.warning("precheck 어댑터: %s tier 없음", ticker)
        return None
    if not isinstance(status, Mapping):
        logger.warning("precheck 어댑터: %s data_status 없음", ticker)
        return None
    if status.get("error"):
        logger.warning("precheck 어댑터: %s data_status 조회 실패(%s)", ticker, status["error"])
        return None
    raw_sources = status.get("sources")
    if not isinstance(raw_sources, Mapping):
        logger.warning("precheck 어댑터: %s sources 없음", ticker)
        return None

    sources: dict[str, SourceStatus] = {}
    for key, value in raw_sources.items():
        if not isinstance(value, Mapping) or value.get("count") is None:
            continue  # 모르는 값은 0으로 채우지 않는다. 필요한 키면 아래에서 None 처리
        try:
            sources[key] = SourceStatus(count=int(value["count"]), latest=_kst_date(value.get("latest")))
        except (TypeError, ValueError):
            logger.warning("precheck 어댑터: %s %s 값을 읽지 못함", ticker, key)
            continue

    missing = required_source_keys(config) - sources.keys()
    if missing:
        logger.warning("precheck 어댑터: %s 필요한 소스 없음 %s", ticker, sorted(missing))
        return None
    return TickerDataStatus(tier=tier, sources=sources)


def data_status_provider(
    resolved_by_ticker: Mapping[str, Mapping[str, Any]],
    config: PrecheckConfig | None = None,
) -> DataStatusProvider:
    """관문1 결과(ticker → `resolve_company` 결과)로 precheck의 `data_status`를 만든다. 없는 종목은 `None`."""
    cfg = config or load_default_config()

    def provide(ticker: str) -> Optional[TickerDataStatus]:
        resolved = resolved_by_ticker.get(ticker)
        if resolved is None:
            logger.warning("precheck 어댑터: %s 관문1 결과 없음", ticker)
            return None
        return ticker_data_status(resolved, cfg)

    return provide


def _tier(value: Any) -> Optional[Tier]:
    try:
        return Tier(value)
    except ValueError:
        return None


def _kst_date(value: Any) -> Optional[date]:
    """ISO 날짜·시각 → KST 날짜. 문서 최신일은 timestamptz라 UTC로 오면 KST 날짜로 바꾼다(앞 10자리 자르기 금지)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        return value
    else:
        text = str(value)
        if len(text) == 10:
            return date.fromisoformat(text)
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return parsed.astimezone(KST).date() if parsed.tzinfo else parsed.date()
