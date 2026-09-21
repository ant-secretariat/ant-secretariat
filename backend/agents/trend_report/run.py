"""트렌드 리포트 에이전트 CLI 진입점.

실행 (레포 루트에서):
    python -m agents.trend_report.run --ticker 005930
"""
import argparse
import logging

from agents.trend_report.config import SUPPORTED_COMPANIES
from agents.trend_report.service import TrendReportAgent
from agents.trend_report.schemas import TrendReportRequest


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Trend Report Agent.")
    parser.add_argument("--ticker", required=True, help="Supported company ticker.")
    parser.add_argument("--query", default=None, help="Optional trend query.")
    parser.add_argument("--date-from", default=None)
    parser.add_argument("--date-to", default=None)
    parser.add_argument("--legacy-markdown", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    agent = TrendReportAgent()
    if args.legacy_markdown:
        path = agent.run()
        print(f"브리핑 생성 완료: {path}")
    else:
        company = SUPPORTED_COMPANIES.get(args.ticker)
        if company is None:
            raise SystemExit(f"지원하지 않는 ticker입니다: {args.ticker}")
        result = agent.run_trend_report(
            TrendReportRequest(
                ticker=company.ticker,
                company=company.name,
                sector=company.sector,
                query=args.query,
                date_from=args.date_from,
                date_to=args.date_to,
            )
        )
        path = agent.save_json(result)
        print(f"트렌드 리포트 JSON 생성 완료: {path}")
