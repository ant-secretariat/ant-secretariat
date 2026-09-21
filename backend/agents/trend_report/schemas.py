from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from agents.trend_report.config import Company


@dataclass(frozen=True)
class ReportChunk:
    chunk_id: str
    report_id: str
    content: str
    score: float
    ticker: str
    company: str
    published_at: str
    title: str
    source: str
    author_org: str
    url: str


@dataclass
class CompanyEvidence:
    company: Company
    as_of_date: date
    lookback_days: int | None
    chunks: list[ReportChunk] = field(default_factory=list)

    @property
    def has_new_report(self) -> bool:
        return self.lookback_days == 1 and bool(self.chunks)

    @property
    def is_fallback(self) -> bool:
        return self.lookback_days is not None and self.lookback_days > 1

    @property
    def latest_report_date(self) -> str | None:
        dates = [chunk.published_at for chunk in self.chunks if chunk.published_at]
        return max(dates) if dates else None


@dataclass(frozen=True)
class TrendReportRequest:
    ticker: str
    company: str
    sector: str = ""
    query: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    as_of_date: str | None = None


@dataclass
class TrendReportResult:
    ticker: str
    company: str
    as_of_date: str
    cards: dict[str, Any]
    evidence: list[dict[str, Any]]
    data_status: dict[str, Any]
    raw_context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company": self.company,
            "as_of_date": self.as_of_date,
            "cards": self.cards,
            "evidence": self.evidence,
            "data_status": self.data_status,
        }
