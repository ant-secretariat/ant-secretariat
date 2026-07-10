import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, RefreshCw } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingBlock } from "../components/LoadingBlock";
import { useAppStore } from "../store/appStore";
import type { InsightFeature } from "../types";

const features: Array<{ id: InsightFeature; label: string }> = [
  { id: "price", label: "주가" },
  { id: "macro", label: "매크로" },
  { id: "disclosure", label: "공시" },
];

export function DashboardPage() {
  const userId = useAppStore((state) => state.userId);
  const selectedCompany = useAppStore((state) => state.selectedCompany);
  const setSelectedCompany = useAppStore((state) => state.setSelectedCompany);
  const selectedFeature = useAppStore((state) => state.selectedFeature);
  const setSelectedFeature = useAppStore((state) => state.setSelectedFeature);
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
  const insightQuery = useQuery({
    queryKey: ["insight-board", activeUserId, selectedCompany?.company, selectedFeature],
    queryFn: () =>
      api.insightBoard({
        user_id: activeUserId,
        companies: selectedCompany ? [selectedCompany.company] : [],
        feature: selectedFeature,
      }),
    enabled: Boolean(activeUserId && selectedCompany),
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
          <p className="eyebrow">Agent E</p>
          <h1>빠른 인사이트</h1>
          <p>기업을 선택하고 주가, 매크로, 공시 데이터를 빠르게 확인합니다.</p>
        </div>
        <button className="secondary-button" onClick={() => companiesQuery.refetch()}>
          <RefreshCw size={16} />
          새로고침
        </button>
      </header>

      <section className="insight-workspace">
        <div className="panel compact-control-panel">
          <div className="control-row">
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
            {selectedCompany ? (
              <div className="selected-company-summary">
                <strong>{selectedCompany.company}</strong>
                <span>{selectedCompany.sector}</span>
              </div>
            ) : null}
            <DataStatusPills status={statusQuery.data?.available} loading={statusQuery.isLoading} />
          </div>
        </div>

        <div className="panel">
          <div className="panel-title">
            <BarChart3 size={18} />
            InsightBoard
          </div>
          <div className="insight-tabs-row">
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
            {selectedCompany ? (
              <span className="muted-text">{selectedCompany.company} 기준</span>
            ) : null}
          </div>
          {insightQuery.isLoading || insightQuery.isFetching ? <LoadingBlock label="인사이트 조회 중" /> : null}
          {insightQuery.error ? <div className="error-box">{insightQuery.error.message}</div> : null}
          {insightQuery.data ? (
            <InsightResult data={insightQuery.data} feature={selectedFeature} />
          ) : null}
        </div>
      </section>
    </div>
  );
}

function DataStatusPills({ status, loading }: { status?: Record<string, boolean>; loading: boolean }) {
  if (loading) return <span className="muted-text">준비 상태 확인 중</span>;
  if (!status) return <span className="muted-text">기업 선택 후 확인</span>;
  const entries = [
    ["가격", status.price_data],
    ["시장", status.macro_data],
    ["공시", status.disclosures],
    ["리포트", status.reports],
  ] as const;
  return (
    <div className="status-pill-row">
      {entries.map(([label, value]) => (
        <span key={label} className={`data-pill ${value ? "ready" : ""}`}>
          {label}
        </span>
      ))}
    </div>
  );
}

function InsightResult({
  data,
  feature,
}: {
  data: { badges: string[]; llm_comment: string; raw_data: unknown };
  feature: InsightFeature;
}) {
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
      <InsightDataView value={data.raw_data} feature={feature} />
    </div>
  );
}

function InsightDataView({ value, feature }: { value: unknown; feature: InsightFeature }) {
  if (feature === "price") return <PriceInsight value={value} />;
  if (feature === "macro") return <MacroInsight value={value} />;
  if (feature === "disclosure") return <DisclosureInsight value={value} />;
  return null;
}

function PriceInsight({ value }: { value: unknown }) {
  const records = Array.isArray(value) ? value.filter(isRecord) : [];
  if (!records.length) return <EmptyState title="주가 데이터가 없습니다" />;
  return (
    <div className="insight-card-grid">
      {records.map((record, index) => {
        const latest = isRecord(record.latest) ? record.latest : {};
        const prices = Array.isArray(record.prices) ? record.prices.filter(isRecord) : [];
        const chartRows = prices
          .slice()
          .reverse()
          .slice(-90)
          .map((row) => ({
            date: String(row.price_date ?? "").slice(5),
            close: Number(row.close ?? 0),
          }));
        return (
          <article className="insight-card large" key={index}>
            <div className="insight-card-header">
              <strong>{formatValue(record.company)}</strong>
              <span>{formatValue(record.ticker)}</span>
            </div>
            <div className="metric-grid">
              <Metric label="현재가" value={money(latest.current_price)} />
              <Metric label="30일 변동성" value={percentFromRatio(latest.volatility_30d)} />
              <Metric label="기준일" value={formatValue(latest.price_date)} />
            </div>
            <SimpleLineChart rows={chartRows} dataKey="close" color="#0f766e" />
          </article>
        );
      })}
    </div>
  );
}

function MacroInsight({ value }: { value: unknown }) {
  const root = Array.isArray(value) && isRecord(value[0]) ? value[0] : value;
  const indicators = isRecord(root) && Array.isArray(root.indicators) ? root.indicators.filter(isRecord) : [];
  if (!indicators.length) return <EmptyState title="시장 지표 데이터가 없습니다" />;
  const cards = indicators.map((indicator) => {
    const records = Array.isArray(indicator.records) ? indicator.records.filter(isRecord) : [];
    const latest = records[0] ?? {};
    const previous = records[1] ?? {};
    const latestValue = Number(latest.value ?? 0);
    const previousValue = Number(previous.value ?? latestValue);
    const delta = latestValue - previousValue;
    return {
      id: String(indicator.indicator_id ?? ""),
      name: macroName(String(indicator.indicator_id ?? ""), String(indicator.indicator_name ?? "")),
      value: latestValue,
      delta,
      date: String(latest.date ?? ""),
      unit: String(indicator.unit ?? ""),
      rows: records
        .slice()
        .reverse()
        .slice(-24)
        .map((row) => ({
          date: String(row.date ?? "").slice(2),
          value: Number(row.value ?? 0),
        })),
    };
  });
  const chartTarget = cards.find((card) => card.id === "USD_KRW") ?? cards[0];
  return (
    <div className="macro-layout">
      <div className="macro-summary-table">
        {cards.map((card) => (
          <div className="macro-summary-row" key={card.id}>
            <span>{card.name}</span>
            <strong>{formatMacroValue(card.value, card.unit)}</strong>
            <em className={card.delta >= 0 ? "up" : "down"}>
              {card.delta >= 0 ? "+" : ""}
              {card.delta.toFixed(2)}
            </em>
          </div>
        ))}
      </div>
      <article className="insight-card large">
        <div className="insight-card-header">
          <strong>{chartTarget.name} 추이</strong>
          <span>{chartTarget.date}</span>
        </div>
        <SimpleLineChart rows={chartTarget.rows} dataKey="value" color="#2563eb" />
      </article>
    </div>
  );
}

function DisclosureInsight({ value }: { value: unknown }) {
  const records = Array.isArray(value) ? value.filter(isRecord) : [];
  const disclosures = records.flatMap((record) =>
    Array.isArray(record.disclosures) ? record.disclosures.filter(isRecord) : [],
  );
  if (!disclosures.length) return <EmptyState title="공시 데이터가 없습니다" />;
  return (
    <div className="disclosure-list">
      {disclosures.slice(0, 10).map((item, index) => (
        <a
          className="disclosure-row"
          href={typeof item.url === "string" ? item.url : undefined}
          target="_blank"
          rel="noreferrer"
          key={`${item.title}-${index}`}
        >
          <div>
            <strong>{formatValue(item.title)}</strong>
            <span>{truncate(formatValue(item.summary), 140)}</span>
          </div>
          <time>{formatValue(item.date)}</time>
        </a>
      ))}
    </div>
  );
}

function SimpleLineChart({
  rows,
  dataKey,
  color,
}: {
  rows: Array<Record<string, number | string>>;
  dataKey: string;
  color: string;
}) {
  if (!rows.length) return <div className="chart-placeholder">차트 데이터가 없습니다.</div>;
  return (
    <div className="chart-box compact">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#e2e8f0" vertical={false} />
          <XAxis dataKey="date" tickLine={false} axisLine={false} />
          <YAxis tickLine={false} axisLine={false} width={72} />
          <Tooltip
            formatter={(entry) =>
              typeof entry === "number" ? entry.toLocaleString("ko-KR") : entry
            }
          />
          <Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={2.3} />
        </LineChart>
      </ResponsiveContainer>
    </div>
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
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

function money(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number) || number === 0) return "-";
  return `${number.toLocaleString("ko-KR")}원`;
}

function percentFromRatio(value: unknown) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  return `${(number * 100).toFixed(2)}%`;
}

function macroName(id: string, fallback: string) {
  return (
    {
      KTB_10Y_KR: "국고채 10년",
      KTB_3Y_KR: "국고채 3년",
      USD_KRW: "원/달러 환율",
      BASE_RATE_KR: "기준금리",
      CPI_KR: "소비자물가",
    }[id] ?? fallback
  );
}

function formatMacroValue(value: number, unit: string) {
  if (!Number.isFinite(value)) return "-";
  if (unit === "KRW") return `${value.toLocaleString("ko-KR")}원`;
  if (unit.includes("연%")) return `${value.toFixed(2)}%`;
  return value.toFixed(2);
}

function truncate(value: string, maxLength: number) {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength)}...`;
}
