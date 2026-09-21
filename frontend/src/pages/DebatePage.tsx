import { useMutation, useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  Circle,
  Loader2,
  Play,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { EmptyState } from "../components/EmptyState";
import { LoadingBlock } from "../components/LoadingBlock";
import { SimulationChart } from "../components/SimulationChart";
import { StatusBadge } from "../components/StatusBadge";
import { useAppStore } from "../store/appStore";
import type { DebateAgenda, DebateArgument, DebateJob, DebatePartialResult, JobStatus, SimulationResult } from "../types";

const terminalStatuses = new Set(["completed", "failed"]);
const statusLabels: Record<string, string> = {
  queued: "분석 준비 중",
  running: "토론 생성 중",
  debate_completed: "토론 완료",
  simulation_running: "시뮬레이션 실행 중",
  completed: "전체 완료",
  failed: "실패",
};

const exampleQuestions = [
  "최근 업황 기준으로 주가 상승 여력이 있는지 분석해줘",
  "실적 개선 가능성과 주요 리스크를 비교해줘",
  "목표주가와 현재가 차이를 근거 중심으로 판단해줘",
  "단기 투자 관점에서 긍정/부정 요인을 토론해줘",
];

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
          <p>찬성 측, 반대 측, 판정 분석과 시뮬레이션 결과를 분석 단위로 확인합니다.</p>
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
            {startMutation.isPending ? <Loader2 className="spin-icon" size={17} /> : <Play size={17} />}
            {startMutation.isPending ? "시작 중" : "시작"}
          </button>
        </div>
        <div className="prompt-chip-row">
          {exampleQuestions.map((question) => (
            <button
              className="prompt-chip"
              key={question}
              onClick={() => setQuery(question)}
              type="button"
            >
              {question}
            </button>
          ))}
        </div>
        {startMutation.isPending ? (
          <LoadingBlock label="분석 작업을 생성하는 중입니다. 잠시 후 진행 상태 화면으로 이동합니다." />
        ) : null}
        {startMutation.error ? <div className="error-box">{startMutation.error.message}</div> : null}
      </section>

      {!jobId ? (
        <EmptyState title="선택된 분석이 없습니다" description="새 토론을 시작하거나 분석 이력에서 기존 토론을 선택하세요." />
      ) : jobQuery.isLoading ? (
        <LoadingBlock label="분석 상태 조회 중" />
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
  const partial = job.partial_result;
  const hasDebate = Boolean(debate?.agendas?.length);
  const hasPartial = Boolean(
    partial?.bull_output?.agendas?.length ||
      partial?.bear_output?.agendas?.length ||
      partial?.judge_output?.overall_verdict,
  );
  const hasSimulation = Boolean(simulation && Object.keys(simulation).length);
  const waitingForDebate = job.status === "queued" || job.status === "running";
  const waitingForSimulation = job.status === "debate_completed" || job.status === "simulation_running";
  const failed = job.status === "failed";

  return (
    <div className="job-layout">
      <section className="panel">
        <div className="panel-toolbar">
          <div>
            <div className="panel-title">작업 상태</div>
          </div>
          <button className="secondary-button" onClick={onRefresh}>
            <RefreshCw size={16} />
            갱신
          </button>
        </div>
        <div className="job-summary-grid">
          <Info label="기업" value={`${job.company} (${job.ticker})`} />
          <Info label="진행 상태" value={statusLabels[job.status] ?? job.status} />
        </div>
        {job.error_message ? (
          <div className="error-box">
            <AlertTriangle size={16} />
            {job.error_message}
          </div>
        ) : null}
      </section>

      <ProgressPanel status={job.status} partial={partial} />

      {failed ? null : waitingForDebate && !hasPartial ? (
        <LoadingBlock label="토론 결과를 생성하는 중입니다" />
      ) : finalBrief ? (
        <section className="panel">
          <div className="panel-title">판정 브리핑</div>
          <p className="comment-box">{typeof finalBrief === "string" ? finalBrief : "최종 브리핑 데이터가 없습니다."}</p>
        </section>
      ) : null}

      {hasDebate ? (
        <section className="agenda-stack">
          {debate!.agendas.map((agenda) => (
            <AgendaCard agenda={agenda} key={agenda.agenda_id} />
          ))}
        </section>
      ) : hasPartial ? (
        <PartialDebateResult partial={partial!} />
      ) : !failed && !waitingForDebate ? (
        <EmptyState title="토론 결과가 없습니다" description="토론 단계가 완료됐지만 표시할 결과가 없습니다." />
      ) : null}

      {hasSimulation ? (
        <SimulationPanel simulation={simulation!} />
      ) : !failed && waitingForSimulation ? (
        <LoadingBlock label={job.status === "simulation_running" ? "시뮬레이션 결과를 계산하는 중입니다" : "시뮬레이션 실행을 준비하는 중입니다"} />
      ) : job.status === "completed" ? (
        <EmptyState title="시뮬레이션 결과가 없습니다" description="분석은 완료됐지만 표시할 시뮬레이션 결과가 없습니다." />
      ) : null}
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
        <div className="winner-pill">{roleLabel(agenda.verdict.winner)}</div>
      </div>
      <div className="argument-grid">
        <ArgumentSide title="찬성 측" summary={agenda.bull.summary} items={agenda.bull.arguments} />
        <ArgumentSide title="반대 측" summary={agenda.bear.summary} items={agenda.bear.arguments} />
      </div>
      <div className="verdict-box">
        <strong>{agenda.verdict.key_point}</strong>
        <span>{agenda.verdict.reasoning}</span>
      </div>
    </article>
  );
}

const progressSteps = [
  { label: "데이터 수집", description: "기업 데이터와 사용자 정보를 불러옵니다." },
  { label: "찬성 측 분석", description: "긍정 투자 근거를 구성합니다." },
  { label: "반대 측 분석", description: "리스크와 반박 근거를 구성합니다." },
  { label: "판정", description: "양쪽 근거를 종합해 결론을 정리합니다." },
  { label: "시뮬레이션", description: "수익률 분포를 계산합니다." },
  { label: "완료", description: "전체 결과를 확인할 수 있습니다." },
];

function ProgressPanel({ status, partial }: { status: JobStatus; partial?: DebatePartialResult }) {
  const currentIndex = progressIndex(status, partial?.stage);
  const failed = status === "failed";
  const completed = status === "completed";

  return (
    <section className="panel progress-panel">
      <div className="panel-title">진행 상태</div>
      {failed ? (
        <div className="error-box">
          <XCircle size={16} />
          분석 처리 중 오류가 발생했습니다. 상단의 작업 상태에서 오류 내용을 확인하세요.
        </div>
      ) : null}
      <div className="progress-step-grid">
        {progressSteps.map((step, index) => {
          const done = !failed && (completed || index < currentIndex);
          const active = !failed && !completed && index === currentIndex;
          const Icon = done ? CheckCircle2 : active ? Loader2 : Circle;
          return (
            <div className={`progress-step ${done ? "done" : ""} ${active ? "active" : ""}`} key={step.label}>
              <Icon className={active ? "spin-icon" : ""} size={18} />
              <div>
                <strong>{step.label}</strong>
                <span>{step.description}</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function progressIndex(status: JobStatus, stage?: string) {
  if (status === "completed") return progressSteps.length - 1;
  if (status === "simulation_running" || status === "debate_completed") return 4;
  if (status === "failed") return -1;
  if (stage === "judge_completed") return 4;
  if (stage === "bear_completed") return 3;
  if (stage === "bull_completed") return 2;
  if (stage === "data_collected") return 1;
  return 0;
}

function PartialDebateResult({ partial }: { partial: DebatePartialResult }) {
  const bullAgendas = partial.bull_output?.agendas ?? [];
  const bearAgendas = partial.bear_output?.agendas ?? [];
  const judge = partial.judge_output?.overall_verdict;

  return (
    <div className="partial-debate-stack">
      {bullAgendas.length ? (
        <PartialAgentPanel title="찬성 측 분석" tone="bull" agendas={bullAgendas} />
      ) : (
        <LoadingBlock label="찬성 측 분석을 생성하는 중입니다" />
      )}
      {bearAgendas.length ? (
        <PartialAgentPanel title="반대 측 분석" tone="bear" agendas={bearAgendas} />
      ) : bullAgendas.length ? (
        <LoadingBlock label="반대 측 분석을 생성하는 중입니다" />
      ) : null}
      {judge ? (
        <section className="panel">
          <div className="panel-title">판정 생성 완료</div>
          <p className="comment-box">{formatUnknown(judge.final_brief) || "판정 결과를 정리했습니다."}</p>
        </section>
      ) : bearAgendas.length ? (
        <LoadingBlock label="판정 브리핑을 생성하는 중입니다" />
      ) : null}
    </div>
  );
}

function PartialAgentPanel({
  title,
  tone,
  agendas,
}: {
  title: string;
  tone: "bull" | "bear";
  agendas: Array<{
    agenda_id?: number;
    agenda_title?: string;
    arguments?: DebateArgument[];
    summary?: string;
  }>;
}) {
  return (
    <section className={`panel partial-agent-panel ${tone}`}>
      <div className="panel-title">{title}</div>
      <div className="partial-agenda-grid">
        {agendas.map((agenda, index) => (
          <article className="partial-agenda-card" key={`${agenda.agenda_id ?? index}-${agenda.agenda_title ?? title}`}>
            <span>Agenda {agenda.agenda_id ?? index + 1}</span>
            <strong>{agenda.agenda_title ?? "분석 아젠다"}</strong>
            {agenda.summary ? <p>{agenda.summary}</p> : null}
            <ul>
              {(agenda.arguments ?? []).slice(0, 2).map((item, itemIndex) => (
                <li key={`${item.title ?? "근거"}-${itemIndex}`}>
                  <strong>{item.title ?? "근거"}</strong>
                  <span>{item.content ?? ""}</span>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
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

function formatUnknown(value: unknown) {
  if (value === null || value === undefined) return "";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function roleLabel(value: string) {
  const labels: Record<string, string> = {
    Bull: "찬성 측",
    bull: "찬성 측",
    Bear: "반대 측",
    bear: "반대 측",
    Judge: "판정",
    judge: "판정",
  };
  return labels[value] ?? value;
}
