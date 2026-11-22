"""에이전트 사이 공용 열거형. API 계약서(docs/api/openapi.yaml) components.schemas와 값이 같다.

backend는 여기서 import해서 쓴다(기획서 v2 3-4절, 공용 계약 위치 Q9). 값을 바꾸려면 계약서를 먼저 고친다.
테스트(processing/tests/test_enums.py)가 계약서와 값이 같은지 확인한다.

    from processing.enums import AgendaId, DataTier, Tier

    AgendaId("valuation")          # 문자열 → 열거형 (없는 값이면 ValueError)
    AgendaId.VALUATION == "valuation"  # str을 상속해 문자열과 그대로 비교·JSON 직렬화된다
"""

from __future__ import annotations

from enum import Enum


class AgendaId(str, Enum):
    """토론 아젠다 ID. get_agent_context의 intent, 온톨로지 agenda_id와 같은 값이다."""

    VALUATION = "valuation"                    # 실적·밸류에이션
    MACRO = "macro"                            # 산업·매크로
    RISK = "risk"                              # 리스크
    GROWTH = "growth"                          # 성장 동력
    SHAREHOLDER_RETURN = "shareholder_return"  # 주주환원
    FLOW = "flow"                              # 수급

    def __str__(self) -> str:
        return self.value


class DataTier(str, Enum):
    """지금 받은 근거의 종류. get_agent_context 결과에 항상 붙는다. 위에서부터 우선한다."""

    REPORT = "report"                    # 애널리스트 리포트 기반
    NEWS_ONLY = "news_only"              # 리포트가 없어서 뉴스로 대체
    DISCLOSURE_ONLY = "disclosure_only"  # 뉴스도 없어서 공시로 대체
    DERIVED_ONLY = "derived_only"        # get_derived_snapshot(시세·재무 계산 근거)로 대체
    MACRO_ONLY = "macro_only"            # 매크로 지표만

    def __str__(self) -> str:
        return self.value


class Tier(str, Enum):
    """종목 등급 (companies.tier). resolve_company가 돌려준다. DataTier와 다른 값이다."""

    T0 = "T0"  # 전 종목, 구조화 데이터만
    T1 = "T1"  # 핵심 종목, 리포트·뉴스·공시 임베딩까지
    T2 = "T2"  # 처음 물어본 종목, 수집 중 (Post-MVP)

    def __str__(self) -> str:
        return self.value


AGENDA_IDS: tuple[str, ...] = tuple(item.value for item in AgendaId)
DATA_TIERS: tuple[str, ...] = tuple(item.value for item in DataTier)
TIERS: tuple[str, ...] = tuple(item.value for item in Tier)


def data_tier_for(report_count: int, news_count: int, disclosure_count: int,
                  derived_available: bool) -> DataTier:
    """근거 건수로 DataTier를 정한다. 리포트 → 뉴스 → 공시 → 계산 근거 → 매크로 순으로 있는 것을 쓴다."""
    if report_count > 0:
        return DataTier.REPORT
    if news_count > 0:
        return DataTier.NEWS_ONLY
    if disclosure_count > 0:
        return DataTier.DISCLOSURE_ONLY
    if derived_available:
        return DataTier.DERIVED_ONLY
    return DataTier.MACRO_ONLY
