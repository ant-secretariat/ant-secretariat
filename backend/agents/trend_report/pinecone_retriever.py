"""Pinecone에서 직접 report_chunks를 조회하는 레거시 마크다운 브리핑 전용 리트리버.

카드형 JSON 결과(`TrendReportAgent.run_trend_report`)는 이 클래스를 쓰지 않고
`agents/trend_report/data_agent_client.py`를 통해 data-pipeline의
processing 함수들을 사용한다. 이 리트리버는 `TrendReportAgent.run()`
(--legacy-markdown) 경로에서만 쓰인다.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from openai import OpenAI
from pinecone import Pinecone

from agents.trend_report.config import (
    LOOKBACK_DAYS,
    MAX_CHUNKS_PER_COMPANY,
    MAX_CHUNKS_PER_REPORT,
    REPORT_NAMESPACE,
    SEARCH_QUERY,
    TOP_K,
    Company,
    require_env,
)
from agents.trend_report.schemas import CompanyEvidence, ReportChunk


class ReportRetriever:
    def __init__(self) -> None:
        self.embedding_client = OpenAI(
            api_key=require_env("UPSTAGE_API_KEY"),
            base_url="https://api.upstage.ai/v1",
        )
        self.embedding_model = "solar-embedding-1-large-query"
        pinecone = Pinecone(api_key=require_env("PINECONE_API_KEY"))
        self.index = pinecone.Index(require_env("PINECONE_INDEX"))

    def retrieve(self, company: Company, as_of_date: date) -> CompanyEvidence:
        query_vector = self._embed(f"{company.name} {company.sector} {SEARCH_QUERY}")
        matches = self.index.query(
            namespace=REPORT_NAMESPACE,
            vector=query_vector,
            top_k=TOP_K,
            include_metadata=True,
            filter={"ticker": {"$eq": company.ticker}},
        ).matches

        for days in LOOKBACK_DAYS:
            # 최근 1일은 실행일과 전일을 포함한다. 날짜 메타데이터만 있는 데이터의
            # 시간 경계를 과도하게 정밀한 것으로 오해하지 않기 위한 정책이다.
            date_from = as_of_date - timedelta(days=days)
            dated_matches = [
                match for match in matches
                if date_from.isoformat()
                <= str((match.metadata or {}).get("date", ""))
                <= as_of_date.isoformat()
                and self._matches_company_title(
                    str((match.metadata or {}).get("title", "")), company
                )
            ]
            chunks = self._normalize(dated_matches)
            if chunks:
                return CompanyEvidence(company, as_of_date, days, chunks)

        return CompanyEvidence(company, as_of_date, None, [])

    @staticmethod
    def _matches_company_title(title: str, company: Company) -> bool:
        """수집 단계에서 잘못 붙은 ticker가 분석 근거로 섞이는 것을 막는다."""
        normalized_title = re.sub(r"\s+", "", title).casefold()
        normalized_company = re.sub(r"\s+", "", company.name).casefold()
        return bool(normalized_company and normalized_company in normalized_title)

    def _embed(self, text: str) -> list[float]:
        response = self.embedding_client.embeddings.create(
            model=self.embedding_model,
            input=text,
        )
        return response.data[0].embedding

    def _normalize(self, matches: list) -> list[ReportChunk]:
        per_report: dict[str, int] = defaultdict(int)
        result: list[ReportChunk] = []

        for match in matches:
            metadata = dict(match.metadata or {})
            chunk_id = metadata.get("chunk_id", match.id)
            report_id = re.sub(r"_chunk_\d+$", "", chunk_id)
            if per_report[report_id] >= MAX_CHUNKS_PER_REPORT:
                continue

            content = metadata.get("content", "").strip()
            if not content:
                continue

            result.append(
                ReportChunk(
                    chunk_id=chunk_id,
                    report_id=report_id,
                    content=content,
                    score=float(match.score),
                    ticker=metadata.get("ticker", ""),
                    company=metadata.get("company", ""),
                    published_at=metadata.get("date", ""),
                    title=metadata.get("title", ""),
                    source=metadata.get("source", ""),
                    author_org=metadata.get("author_org", ""),
                    url=metadata.get("url", ""),
                )
            )
            per_report[report_id] += 1
            if len(result) >= MAX_CHUNKS_PER_COMPANY:
                break

        return result
