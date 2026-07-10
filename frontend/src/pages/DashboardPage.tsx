import { useMutation, useQuery } from "@tanstack/react-query";
import { BarChart3, Building2, Database, Play, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingBlock } from "../components/LoadingBlock";
import { useAppStore } from "../store/appStore";
import type { Company, InsightFeature } from "../types";

const features: Array<{ id: InsightFeature; label: string }> = [
  { id: "price", label: "주가" },
  { id: "macro", label: "매크로" },
  { id: "disclosure", label: "공시" },
];

export function DashboardPage() {
  const navigate = useNavigate();
  const userId = useAppStore((state) => state.userId);
  const selectedCompany = useAppStore((state) => state.selectedCompany);
  const setSelectedCompany = useAppStore((state) => state.setSelectedCompany);
  const selectedFeature = useAppStore((state) => state.selectedFeature);
  const setSelectedFeature = useAppStore((state) => state.setSelectedFeature);
  const setCurrentJobId = useAppStore((state) => state.setCurrentJobId);
  const activeUserId = userId ?? "";

  const companiesQuery = useQuery({
    queryKey: ["companies"],
    queryFn: api.companies,
  });
  const statusQuery = useQuery({
    queryKey: ["data-status", selectedCompany?.ticker],
    queryFn: () => api.dataStatus(selectedCompany!.ticker),
    enabled: Boolean(selectedCompany),
  });
  const insightMutation = useMutation({
    mutationFn: () =>
      api.insightBoard({
        user_id: activeUserId,
        companies: selectedCompany ? [selectedCompany.company] : [],
        feature: selectedFeature,
      }),
  });
  const debateMutation = useMutation({
    mutationFn: () =>
      api.startDebate({
        user_id: activeUserId,
        company: selectedCompany!.company,
        query: `${selectedCompany!.company}의 업황과 주가 전망을 분석해줘`,
      }),
    onSuccess: (data) => {
      setCurrentJobId(data.job_id);
      navigate(`/debate/${data.job_id}`);
    },
  });

  const companies = companiesQuery.data ?? [];

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Agent E</p>
          <h1>빠른 인사이트</h1>
          <p>기업을 선택하고 주가, 매크로, 공시 데이터를 빠르게 확인합니다.</p>
        </div>
        <button className="secondary-button" onClick={() => companiesQuery.refetch()}>
          <RefreshCw size={16} />
          새로고침
        </button>
      </header>

      <section className="dashboard-grid">
        <div className="panel">
          <div className="panel-title">
            <Building2 size={18} />
            분석 대상
          </div>
          {companiesQuery.isLoading ? (
            <LoadingBlock />
          ) : (
            <div className="company-list">
              {companies.map((company) => (
                <button
                  key={company.ticker}
                  className={`company-row ${
                    selectedCompany?.ticker === company.ticker ? "selected" : ""
                  }`}
                  onClick={() => setSelectedCompany(company)}
                  type="button"
                >
                  <div>
                    <strong>{company.company}</strong>
                    <span>{company.sector}</span>
                  </div>
                  <code>{company.ticker}</code>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">
            <Database size={18} />
            분석 준비 상태
          </div>
          {selectedCompany ? (
            statusQuery.isLoading ? (
              <LoadingBlock />
            ) : statusQuery.data ? (
              <DataStatusGrid status={statusQuery.data.available} />
            ) : (
              <EmptyState title="상태 데이터 없음" />
            )
          ) : (
            <EmptyState title="기업을 선택하세요" description="좌측 목록에서 분석할 기업을 선택합니다." />
          )}
        </div>

        <div className="panel wide-panel">
          <div className="panel-title">
            <BarChart3 size={18} />
            InsightBoard
          </div>
          <div className="feature-tabs">
            {features.map((feature) => (
              <button
                key={feature.id}
                className={selectedFeature === feature.id ? "active" : ""}
                onClick={() => setSelectedFeature(feature.id)}
                type="button"
              >
                {feature.label}
              </button>
            ))}
          </div>
          <div className="action-row">
            <button
              className="primary-button"
              disabled={!selectedCompany || insightMutation.isPending}
              onClick={() => insightMutation.mutate()}
            >
              <Play size={17} />
              조회
            </button>
            <button
              className="secondary-button strong"
              disabled={!selectedCompany || debateMutation.isPending}
              onClick={() => debateMutation.mutate()}
            >
              <Play size={17} />
              토론·시뮬레이션으로 이동
            </button>
          </div>
          {insightMutation.isPending ? <LoadingBlock label="InsightBoard 조회 중" /> : null}
          {insightMutation.error ? <div className="error-box">{insightMutation.error.message}</div> : null}
          {insightMutation.data ? <InsightResult data={insightMutation.data} /> : null}
          {debateMutation.error ? <div className="error-box">{debateMutation.error.message}</div> : null}
        </div>
      </section>
    </div>
  );
}

function DataStatusGrid({ status }: { status: Record<string, boolean> }) {
  const entries = [
    ["분석 리포트", status.reports],
    ["뉴스", status.news],
    ["공시", status.disclosures],
    ["가격 데이터", status.price_data],
    ["시장 지표", status.macro_data],
    ["목표주가", status.target_price_data],
  ] as const;
  return (
    <div className="status-grid">
      {entries.map(([label, value]) => (
        <div key={label} className="status-cell">
          <span>{label}</span>
          <strong className={value ? "positive" : "muted"}>{value ? "준비됨" : "없음"}</strong>
        </div>
      ))}
    </div>
  );
}

function InsightResult({ data }: { data: { badges: string[]; llm_comment: string; raw_data: unknown } }) {
  return (
    <div className="result-stack">
      <div className="badge-row">
        {data.badges.map((badge) => (
          <span className="soft-badge" key={badge}>
            {badge}
          </span>
        ))}
      </div>
      {data.llm_comment ? <p className="comment-box">{data.llm_comment}</p> : null}
      <InsightDataView value={data.raw_data} />
    </div>
  );
}

function InsightDataView({ value }: { value: unknown }) {
  if (Array.isArray(value)) {
    if (!value.length) return <EmptyState title="조회된 데이터가 없습니다" />;
    return (
      <div className="insight-card-grid">
        {value.map((item, index) => (
          <InsightRecordCard key={index} value={item} title={`데이터 ${index + 1}`} />
        ))}
      </div>
    );
  }
  if (isRecord(value)) {
    return <InsightRecordCard value={value} title="조회 데이터" />;
  }
  return <div className="empty-state">표시할 수 있는 데이터가 없습니다.</div>;
}

function InsightRecordCard({ value, title }: { value: unknown; title: string }) {
  if (!isRecord(value)) {
    return (
      <div className="insight-card">
        <strong>{title}</strong>
        <span>{formatValue(value)}</span>
      </div>
    );
  }

  const heading = [value.company, value.ticker].filter(Boolean).join(" · ") || title;
  const scalarEntries = Object.entries(value).filter(([, entryValue]) => isScalar(entryValue));
  const collectionEntries = Object.entries(value).filter(([, entryValue]) => !isScalar(entryValue));

  return (
    <article className="insight-card">
      <div className="insight-card-header">
        <strong>{heading}</strong>
        {typeof value.sector === "string" ? <span>{value.sector}</span> : null}
      </div>
      {scalarEntries.length ? (
        <div className="compact-kv-grid">
          {scalarEntries.map(([key, entryValue]) => (
            <div className="compact-kv" key={key}>
              <span>{labelize(key)}</span>
              <strong>{formatValue(entryValue)}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {collectionEntries.map(([key, entryValue]) => (
        <NestedPreview key={key} name={key} value={entryValue} />
      ))}
    </article>
  );
}

function NestedPreview({ name, value }: { name: string; value: unknown }) {
  if (Array.isArray(value)) {
    return (
      <div className="nested-preview">
        <div className="nested-title">
          <span>{labelize(name)}</span>
          <strong>{value.length.toLocaleString("ko-KR")}건</strong>
        </div>
        {value.length ? <MiniTable rows={value.slice(0, 5)} /> : <span className="muted-text">데이터 없음</span>}
      </div>
    );
  }
  if (isRecord(value)) {
    return (
      <div className="nested-preview">
        <div className="nested-title">
          <span>{labelize(name)}</span>
        </div>
        <div className="compact-kv-grid">
          {Object.entries(value)
            .slice(0, 8)
            .map(([key, entryValue]) => (
              <div className="compact-kv" key={key}>
                <span>{labelize(key)}</span>
                <strong>{formatValue(entryValue)}</strong>
              </div>
            ))}
        </div>
      </div>
    );
  }
  return null;
}

function MiniTable({ rows }: { rows: unknown[] }) {
  const objectRows = rows.filter(isRecord);
  if (!objectRows.length) {
    return <span className="muted-text">{rows.map(formatValue).join(", ")}</span>;
  }
  const columns = pickColumns(objectRows);
  return (
    <div className="mini-table-wrap">
      <table className="mini-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{labelize(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {objectRows.map((row, index) => (
            <tr key={index}>
              {columns.map((column) => (
                <td key={column}>{formatValue(row[column])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function pickColumns(rows: Array<Record<string, unknown>>) {
  const preferred = [
    "date",
    "price_date",
    "published_at",
    "disclosed_at",
    "title",
    "report_name",
    "close",
    "value",
    "target_price",
    "source",
  ];
  const keys = new Set(rows.flatMap((row) => Object.keys(row)));
  const selected = preferred.filter((key) => keys.has(key));
  for (const key of keys) {
    if (selected.length >= 5) break;
    if (!selected.includes(key) && isScalar(rows.find((row) => row[key] !== undefined)?.[key])) {
      selected.push(key);
    }
  }
  return selected.slice(0, 5);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isScalar(value: unknown) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString("ko-KR") : value.toFixed(2);
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return `${value.length.toLocaleString("ko-KR")}건`;
  if (isRecord(value)) return `${Object.keys(value).length.toLocaleString("ko-KR")}개 항목`;
  return String(value);
}

function labelize(key: string) {
  const labels: Record<string, string> = {
    ticker: "티커",
    company: "기업",
    sector: "섹터",
    latest: "최근 데이터",
    prices: "주가",
    indicators: "지표",
    disclosures: "공시",
    date: "날짜",
    price_date: "날짜",
    published_at: "발행일",
    disclosed_at: "공시일",
    close: "종가",
    value: "값",
    title: "제목",
    report_name: "보고서명",
    source: "출처",
    target_price: "목표주가",
    volatility_30d: "30일 변동성",
    current_price: "현재가",
  };
  return labels[key] ?? "정보";
}
