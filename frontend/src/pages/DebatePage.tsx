import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Play, RefreshCw } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingBlock } from "../components/LoadingBlock";
import { SimulationChart } from "../components/SimulationChart";
import { StatusBadge } from "../components/StatusBadge";
import { useAppStore } from "../store/appStore";
import type { DebateAgenda, DebateJob, SimulationResult } from "../types";

const terminalStatuses = new Set(["completed", "failed"]);
const statusLabels: Record<string, string> = {
  queued: "분석 준비 중",
  running: "토론 생성 중",
  debate_completed: "토론 완료",
  simulation_running: "시뮬레이션 실행 중",
  completed: "전체 완료",
  failed: "실패",
};

export function DebatePage() {
  const params = useParams();
  const navigate = useNavigate();
  const userId = useAppStore((state) => state.userId);
  const selectedCompany = useAppStore((state) => state.selectedCompany);
  const setCurrentJobId = useAppStore((state) => state.setCurrentJobId);
  const [query, setQuery] = useState("");
  const jobId = params.jobId;
  const activeUserId = userId ?? "";

  const jobQuery = useQuery({
    queryKey: ["debate-job", jobId],
    queryFn: () => api.debateJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (queryInfo) => {
      const status = queryInfo.state.data?.status;
      return status && !terminalStatuses.has(status) ? 2500 : false;
    },
  });

  const startMutation = useMutation({
    mutationFn: () =>
      api.startDebate({
        user_id: activeUserId,
        company: selectedCompany!.company,
        query: query || `${selectedCompany!.company}의 업황과 주가 전망을 분석해줘`,
      }),
    onSuccess: (data) => {
      setCurrentJobId(data.job_id);
      navigate(`/debate/${data.job_id}`);
    },
  });

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Debate</p>
          <h1>토론 분석</h1>
          <p>Bull, Bear, Judge 분석과 시뮬레이션 결과를 job 단위로 확인합니다.</p>
        </div>
        {jobQuery.data ? <StatusBadge status={jobQuery.data.status} /> : null}
      </header>

      <section className="panel">
        <div className="panel-title">새 토론 시작</div>
        <div className="debate-start-row">
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={
              selectedCompany
                ? `${selectedCompany.company}에 대해 궁금한 점을 입력하세요`
                : "대시보드에서 기업을 먼저 선택하세요"
            }
          />
          <button
            className="primary-button"
            disabled={!selectedCompany || startMutation.isPending}
            onClick={() => startMutation.mutate()}
          >
            <Play size={17} />
            시작
          </button>
        </div>
        {startMutation.error ? <div className="error-box">{startMutation.error.message}</div> : null}
      </section>

      {!jobId ? (
        <EmptyState title="선택된 job이 없습니다" description="새 토론을 시작하거나 이력에서 job을 선택하세요." />
      ) : jobQuery.isLoading ? (
        <LoadingBlock label="job 상태 조회 중" />
      ) : jobQuery.error ? (
        <div className="error-box">{jobQuery.error.message}</div>
      ) : jobQuery.data ? (
        <JobDetail job={jobQuery.data} onRefresh={() => jobQuery.refetch()} />
      ) : null}
    </div>
  );
}

function JobDetail({ job, onRefresh }: { job: DebateJob; onRefresh: () => void }) {
  const debate = job.debate_result?.debate_result;
  const simulation = job.simulation_result as SimulationResult | undefined;
  const finalBrief = debate?.judge?.overall_verdict?.final_brief;

  return (
    <div className="job-layout">
      <section className="panel">
        <div className="panel-toolbar">
          <div>
            <div className="panel-title">작업 상태</div>
            <p className="muted-text">분석 번호 {shortId(job.job_id)}</p>
          </div>
          <button className="secondary-button" onClick={onRefresh}>
            <RefreshCw size={16} />
            갱신
          </button>
        </div>
        <div className="job-summary-grid">
          <Info label="기업" value={`${job.company} (${job.ticker})`} />
          <Info label="진행 상태" value={statusLabels[job.status] ?? job.status} />
          <Info label="생성" value={new Date(job.created_at).toLocaleString("ko-KR")} />
          <Info label="갱신" value={new Date(job.updated_at).toLocaleString("ko-KR")} />
        </div>
        {job.error_message ? (
          <div className="error-box">
            <AlertTriangle size={16} />
            {job.error_message}
          </div>
        ) : null}
      </section>

      {debate ? (
        <section className="panel">
          <div className="panel-title">Judge 브리핑</div>
          <p className="comment-box">
            {typeof finalBrief === "string" ? finalBrief : "최종 브리핑 데이터가 없습니다."}
          </p>
        </section>
      ) : null}

      {debate?.agendas?.length ? (
        <section className="agenda-stack">
          {debate.agendas.map((agenda) => (
            <AgendaCard agenda={agenda} key={agenda.agenda_id} />
          ))}
        </section>
      ) : (
        <EmptyState title="토론 결과 대기 중" description="상태가 debate_completed 이상이면 결과가 표시됩니다." />
      )}

      {simulation && Object.keys(simulation).length ? (
        <SimulationPanel simulation={simulation} />
      ) : (
        <EmptyState title="시뮬레이션 결과 대기 중" description="상태가 completed가 되면 차트가 표시됩니다." />
      )}
    </div>
  );
}

function AgendaCard({ agenda }: { agenda: DebateAgenda }) {
  return (
    <article className="panel agenda-card">
      <div className="agenda-header">
        <div>
          <span>Agenda {agenda.agenda_id}</span>
          <h2>{agenda.agenda_title}</h2>
        </div>
        <div className="winner-pill">{agenda.verdict.winner}</div>
      </div>
      <div className="argument-grid">
        <ArgumentSide title="Bull" summary={agenda.bull.summary} items={agenda.bull.arguments} />
        <ArgumentSide title="Bear" summary={agenda.bear.summary} items={agenda.bear.arguments} />
      </div>
      <div className="verdict-box">
        <strong>{agenda.verdict.key_point}</strong>
        <span>{agenda.verdict.reasoning}</span>
      </div>
    </article>
  );
}

function ArgumentSide({
  title,
  summary,
  items,
}: {
  title: string;
  summary: string;
  items: DebateAgenda["bull"]["arguments"];
}) {
  return (
    <div className="argument-side">
      <div className="argument-title">
        <span>{title}</span>
        <ArrowRight size={15} />
      </div>
      <p>{summary}</p>
      <ul>
        {(items ?? []).slice(0, 3).map((item, index) => (
          <li key={`${item.title}-${index}`}>
            <strong>{item.title ?? "근거"}</strong>
            <span>{item.content ?? ""}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SimulationPanel({ simulation }: { simulation: SimulationResult }) {
  const chartPaths = simulation.chart_data?.base;
  const summaryRows = useMemo(
    () => [
      { label: "예상 수익률", value: pct(simulation.summary?.expected_return_pct) },
      { label: "상승 확률", value: pct(simulation.summary?.upside_probability) },
      { label: "변동성", value: pct(simulation.summary?.volatility) },
      {
        label: "현재가",
        value: simulation.current_price ? simulation.current_price.toLocaleString("ko-KR") : "-",
      },
    ],
    [simulation],
  );

  return (
    <section className="panel">
      <div className="panel-title">시뮬레이션</div>
      {simulation.error ? <div className="error-box">{simulation.message ?? simulation.error}</div> : null}
      <div className="metric-grid">
        {summaryRows.map((row) => (
          <div className="metric-card" key={row.label}>
            <span>{row.label}</span>
            <strong>{row.value}</strong>
          </div>
        ))}
      </div>
      <SimulationChart paths={chartPaths} />
      {simulation.interpretation ? <p className="comment-box">{simulation.interpretation}</p> : null}
    </section>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="info-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function pct(value?: number) {
  return typeof value === "number" ? `${value.toFixed(2)}%` : "-";
}

function shortId(value: string) {
  return value.replace(/^debate_/, "").slice(0, 8);
}
