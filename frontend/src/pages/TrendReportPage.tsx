import { useMutation, useQuery } from "@tanstack/react-query";
import { FileText, RefreshCw, Sparkles } from "lucide-react";
import { useEffect } from "react";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingBlock } from "../components/LoadingBlock";
import { useAppStore } from "../store/appStore";
import type { TrendReportResult } from "../types";

export function TrendReportPage() {
  const selectedCompany = useAppStore((state) => state.selectedCompany);
  const setSelectedCompany = useAppStore((state) => state.setSelectedCompany);

  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: api.companies,
  });

  const reportMutation = useMutation({
    mutationFn: () =>
      api.trendReport({
        company: selectedCompany!.company,
      }),
  });

  const companies = companiesQuery.data ?? [];

  useEffect(() => {
    if (!selectedCompany && companies.length) {
      setSelectedCompany(companies[0]);
    }
  }, [companies, selectedCompany, setSelectedCompany]);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Trend Report</p>
          <h1>트렌드 리포트</h1>
          <p>기업을 선택하면 최근 리포트와 뉴스 흐름을 요약합니다.</p>
        </div>
      </header>

      <section className="panel compact-control-panel">
        <div className="trend-control-grid">
          <label>
            <span>분석 대상</span>
            <select
              value={selectedCompany?.ticker ?? ""}
              onChange={(event) => {
                const company = companies.find((item) => item.ticker === event.target.value);
                setSelectedCompany(company);
              }}
              disabled={companiesQuery.isLoading}
            >
              <option value="">기업 선택</option>
              {companies.map((company) => (
                <option value={company.ticker} key={company.ticker}>
                  {company.company}
                </option>
              ))}
            </select>
          </label>
          <button
            className="primary-button"
            disabled={!selectedCompany || reportMutation.isPending}
            onClick={() => reportMutation.mutate()}
            type="button"
          >
            {reportMutation.isPending ? <RefreshCw className="spin-icon" size={16} /> : <Sparkles size={16} />}
            생성
          </button>
        </div>
      </section>

      {reportMutation.isPending ? <LoadingBlock label="트렌드 리포트 생성 중" /> : null}
      {reportMutation.error ? <div className="error-box">{reportMutation.error.message}</div> : null}
      {reportMutation.data ? (
        <TrendReportResultView report={reportMutation.data} />
      ) : reportMutation.isIdle ? (
        <EmptyState title="생성된 리포트가 없습니다" description="기업을 선택하고 트렌드 리포트를 생성하세요." />
      ) : null}
    </div>
  );
}

function TrendReportResultView({ report }: { report: TrendReportResult }) {
  const cards = report.cards ?? {};
  const target = cards.target_price_trend ?? {};

  return (
    <div className="trend-report-stack">
      <section className="panel trend-report-header">
        <div className="panel-toolbar">
          <div>
            <div className="panel-title">
              <FileText size={18} />
              {report.company} 리포트
            </div>
            <p className="muted-text">기준일 {report.as_of_date}</p>
          </div>
        </div>
        {target.comment ? <p className="comment-box">{formatValue(target.comment)}</p> : null}
      </section>

      <section className="panel">
        <div className="panel-title">핵심 요약</div>
        {cards.summary?.length ? (
          <ul className="summary-list">
            {cards.summary.map((item, index) => (
              <li key={`${item}-${index}`}>{item}</li>
            ))}
          </ul>
        ) : (
          <EmptyState title="요약 데이터가 없습니다" />
        )}
      </section>

      <div className="trend-card-grid">
        <FactorPanel title="긍정 요인" items={cards.positive_factors} />
        <FactorPanel title="리스크 요인" items={cards.risk_factors} />
        <FactorPanel title="뉴스 이슈" items={cards.news_issue_cards} />
        <section className="panel">
          <div className="panel-title">목표주가</div>
          <div className="compact-kv-grid">
            <Metric label="평균" value={money(target.avg_target_price)} />
            <Metric label="최저" value={money(target.min_target_price)} />
            <Metric label="최고" value={money(target.max_target_price)} />
          </div>
        </section>
      </div>

      {cards.macro_comment ? (
        <section className="panel">
          <div className="panel-title">시장 환경 코멘트</div>
          <p className="comment-box">{cards.macro_comment}</p>
        </section>
      ) : null}
    </div>
  );
}

function FactorPanel({ title, items }: { title: string; items?: Array<Record<string, unknown>> }) {
  return (
    <section className="panel">
      <div className="panel-title">{title}</div>
      {items?.length ? (
        <div className="factor-list">
          {items.map((item, index) => (
            <article className="factor-item" key={`${formatValue(item.title)}-${index}`}>
              <strong>{formatValue(item.title || item.broker || `항목 ${index + 1}`)}</strong>
              <span>{formatValue(item.description || item.view)}</span>
            </article>
          ))}
        </div>
      ) : (
        <p className="muted-empty-text">{title} 데이터가 없습니다.</p>
      )}
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-card">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function money(value: unknown) {
  return typeof value === "number" ? value.toLocaleString("ko-KR") : formatValue(value);
}

function formatValue(value: unknown) {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return value.toLocaleString("ko-KR");
  if (typeof value === "string") return value;
  return JSON.stringify(value);
}
