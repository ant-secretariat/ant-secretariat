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
        user_id: userId,
        companies: selectedCompany ? [selectedCompany.company] : [],
        feature: selectedFeature,
      }),
  });
  const debateMutation = useMutation({
    mutationFn: () =>
      api.startDebate({
        user_id: userId,
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
          <p className="eyebrow">Dashboard</p>
          <h1>기업 분석 대시보드</h1>
          <p>지원 기업의 데이터 상태를 확인하고 빠른 인사이트 또는 토론 분석을 실행합니다.</p>
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
            지원 기업
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
            데이터 상태
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
              인사이트 조회
            </button>
            <button
              className="secondary-button strong"
              disabled={!selectedCompany || debateMutation.isPending}
              onClick={() => debateMutation.mutate()}
            >
              <Play size={17} />
              토론 시작
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
  const entries = Object.entries(status);
  return (
    <div className="status-grid">
      {entries.map(([key, value]) => (
        <div key={key} className="status-cell">
          <span>{key}</span>
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
      <pre className="json-preview">{JSON.stringify(data.raw_data, null, 2)}</pre>
    </div>
  );
}
