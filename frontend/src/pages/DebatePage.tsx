import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ThumbsDown, ThumbsUp } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { DebateChat, plainNames } from "../components/DebateChat";
import { SimulationChart, simulationStats } from "../components/SimulationChart";
import {
  AiNote,
  Ant,
  Button,
  Chip,
  DebateStepper,
  Disclaimer,
  ErrorText,
  OptionCard,
  Skeleton,
  Tip,
  TopBar,
} from "../components/ui";
import { profiles, sectorLabel } from "../data/onboarding";
import { debateStep, isOutOfScope, stepBanner, stepHeadline } from "../lib/debate";
import { useAppStore } from "../store/appStore";
import type { Company, DebateJob, SimulationResult } from "../types";

const terminal = new Set(["completed", "failed"]);
const topics = ["목표주가가 오른 근거", "최근 쟁점", "위험 요인"];
const scopeTopics = ["최근 리포트의 쟁점", "목표주가가 바뀐 근거", "환율이 바뀌면 받는 영향"];

export function DebatePage() {
  const { jobId } = useParams();
  return jobId ? <JobView jobId={jobId} /> : <StartView />;
}

function StartView() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const userId = useAppStore((state) => state.userId) ?? "";
  const setCurrentJobId = useAppStore((state) => state.setCurrentJobId);
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const context = useQuery({
    queryKey: ["user-context", userId],
    queryFn: () => api.userContext(userId),
    retry: false,
  });
  const [sector, setSector] = useState<string>();
  const [company, setCompany] = useState<Company>();
  const [topic, setTopic] = useState<string>();
  const [text, setText] = useState("");
  const [screen, setScreen] = useState<"form" | "scope" | "collecting">("form");

  const all = companies.data ?? [];
  const sectors = context.data?.interest_sectors?.length
    ? context.data.interest_sectors
    : [...new Set(all.map((c) => c.sector))];
  const activeSector = sector ?? sectors[0];
  const inSector = all.filter((c) => c.sector === activeSector);
  const activeCompany = company && company.sector === activeSector ? company : inSector[0];

  const start = useMutation({
    mutationFn: async (query: string) => {
      const status = await api.dataStatus(activeCompany!.ticker);
      if (!status.available.reports) return null;
      return api.startDebate({ user_id: userId, company: activeCompany!.company, query });
    },
    onSuccess: (data) => {
      if (!data) return setScreen("collecting");
      setCurrentJobId(data.job_id);
      client.invalidateQueries({ queryKey: ["user-jobs", userId] });
      navigate(`/debate/${data.job_id}`);
    },
  });

  const begin = (override?: string) => {
    const query = override ?? (text.trim() || topic || `${activeCompany!.company}의 최근 쟁점`);
    if (isOutOfScope(query)) return setScreen("scope");
    setScreen("form");
    start.mutate(query);
  };

  if (screen === "scope") {
    return (
      <div className="screen">
        <TopBar title="찬반 토론" back={() => setScreen("form")} />
        <Ant kind="analysis" size={100} />
        <h2 className="display gap-top">
          단기 주가 예측은
          <br />
          도와드리기 어려워요
        </h2>
        <p className="lead">아래 주제는 함께 살펴볼 수 있어요.</p>
        <div className="options" role="radiogroup" aria-label="살펴볼 수 있는 주제">
          {scopeTopics.map((t) => (
            <OptionCard key={t} selected={false} onClick={() => begin(`${activeCompany?.company} ${t}`)}>
              {t}
            </OptionCard>
          ))}
        </div>
      </div>
    );
  }

  if (screen === "collecting") {
    return (
      <div className="screen">
        <TopBar title="찬반 토론" back={() => setScreen("form")} />
        <Ant kind="alert" size={100} />
        <h2 className="display gap-top">아직 자료를 모으는 중이에요</h2>
        <p className="lead">내일 다시 확인해 주세요.</p>
        <Button variant="secondary" onClick={() => navigate(`/trend-report/${activeCompany?.ticker}`)}>
          트렌드 리포트 보기
        </Button>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar title="찬반 토론" settings />
      <div className="hero-row">
        <Ant kind="analysis" size={84} />
        <h2 className="display">
          어떤 종목을
          <br />
          같이 볼까요?
        </h2>
      </div>
      {companies.isLoading ? <Skeleton /> : null}
      {companies.error ? <ErrorText>종목 목록을 불러오지 못했어요.</ErrorText> : null}

      <h3 className="field-label">내 관심 산업</h3>
      <div className="chips">
        {sectors.map((s) => (
          <Chip key={s} selected={s === activeSector} onClick={() => setSector(s)}>
            {sectorLabel(s)}
          </Chip>
        ))}
      </div>

      <h3 className="field-label">종목</h3>
      <div className="chips">
        {inSector.map((c) => (
          <Chip key={c.ticker} selected={c.ticker === activeCompany?.ticker} onClick={() => setCompany(c)}>
            {c.company}
          </Chip>
        ))}
      </div>

      <h3 className="field-label">궁금한 주제 (선택)</h3>
      <div className="chips">
        {topics.map((t) => (
          <Chip key={t} selected={t === topic} onClick={() => setTopic(t === topic ? undefined : t)}>
            {t}
          </Chip>
        ))}
      </div>

      <div className="field">
        <label htmlFor="ask">직접 물어보기 (선택)</label>
        <input
          id="ask"
          maxLength={100}
          value={text}
          placeholder="100자까지 쓸 수 있어요"
          onChange={(e) => setText(e.target.value)}
        />
        <p className="helper">비워두면 기본 질문으로 시작해요.</p>
      </div>

      {start.error ? <ErrorText>토론을 시작하지 못했어요. 다시 시도해 주세요.</ErrorText> : null}
      <Button disabled={!activeCompany || start.isPending} onClick={() => begin()}>
        {start.isPending ? "시작하고 있어요" : "토론 시작"}
      </Button>
      <p className="caption gap-top-sm">약 2~3분 걸리고, 이력에 저장돼요.</p>
      <Disclaimer />
    </div>
  );
}

function JobView({ jobId }: { jobId: string }) {
  const job = useQuery({
    queryKey: ["debate-job", jobId],
    queryFn: () => api.debateJob(jobId),
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status && terminal.has(status) ? false : 2500;
    },
  });

  if (job.isLoading) {
    return (
      <div className="screen">
        <TopBar title="토론" back="/debate" />
        <Skeleton />
      </div>
    );
  }
  if (job.error || !job.data) {
    return (
      <div className="screen">
        <TopBar title="토론" back="/debate" />
        <ErrorText>토론을 불러오지 못했어요.</ErrorText>
        <Button variant="secondary" onClick={() => job.refetch()}>
          다시 시도
        </Button>
      </div>
    );
  }
  const data = job.data;
  return data.status === "queued" || data.status === "running" || data.status === "failed" ? (
    <ProgressView job={data} />
  ) : (
    <ResultView job={data} />
  );
}

function ProgressView({ job }: { job: DebateJob }) {
  const step = debateStep(job);
  const seconds = useElapsed(job.created_at);
  const bulls = job.partial_result?.bull_output?.agendas ?? [];
  const bears = job.partial_result?.bear_output?.agendas ?? [];
  // 반대 측이 첫 주장부터 차례로 답하도록, 그 전에는 첫 아젠다만 보여 준다.
  const agendas = (bears.length ? bulls : bulls.slice(0, 1)).map((a, i) => ({
    id: a.agenda_id,
    title: a.agenda_title,
    bull: a,
    bear: bears[i],
  }));
  const typing = step === 1 ? "bull" : step === 2 ? "bear" : step >= 3 ? "judge" : undefined;

  return (
    <div className="screen">
      <TopBar title={`${job.company} 토론`} back="/history" />
      <DebateStepper current={step} />
      {job.status === "failed" ? (
        <ErrorText>분석을 마치지 못했어요. 이력에서 다시 시도해 주세요.</ErrorText>
      ) : (
        <>
          {step === 0 ? (
            <div className="hero-row">
              <Ant kind="analysis" size={84} />
              <h2 className="display">{stepHeadline[step]}</h2>
            </div>
          ) : (
            <h2 className="chat-status">{stepBanner[step]}</h2>
          )}
          <p className="caption">
            {Math.floor(seconds / 60)}분 {seconds % 60}초 지났어요. 보통 2~3분 걸려요.
          </p>
          <DebateChat agendas={agendas} typing={typing} live />
          <Tip>다른 화면을 봐도 분석은 계속돼요. 이력에서 다시 열 수 있어요.</Tip>
        </>
      )}
      <Disclaimer />
    </div>
  );
}

function useElapsed(iso: string) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  return Math.max(0, Math.floor((now - new Date(iso).getTime()) / 1000));
}

function ResultView({ job }: { job: DebateJob }) {
  const [showSim, setShowSim] = useState(false);
  const debate = job.debate_result?.debate_result;
  const verdict = debate?.judge?.overall_verdict ?? {};
  const brief = plainNames(String(verdict.final_brief ?? ""));
  const [headline, ...rest] = brief.split(/(?<=[.!?요다])\s+/);
  const agendas = debate?.agendas ?? [];
  const simulation = job.simulation_result as SimulationResult | undefined;
  const hasSim = Boolean(simulation && Object.keys(simulation).length);
  const simWaiting = job.status === "debate_completed" || job.status === "simulation_running";
  const userId = useAppStore((state) => state.userId) ?? "";
  const context = useQuery({
    queryKey: ["user-context", userId],
    queryFn: () => api.userContext(userId),
    retry: false,
  });
  const focus = profiles[context.data?.risk_profile ?? ""]?.focus;
  const keyPoints = agendas.map((a) => a.verdict?.key_point).filter(Boolean).slice(0, 2);

  return (
    <div className="screen">
      <TopBar title={`${job.company} 토론 결과`} back="/history" />
      <section className="verdict">
        <h2>{headline || "판정 결과를 정리했어요."}</h2>
        {rest.length ? <p>{rest.join(" ")}</p> : null}
      </section>

      {showSim && hasSim ? (
        <SimulationCard simulation={simulation!} />
      ) : (
        <section className="card sim-cta">
          <h3>이 위험이 가격에 어느 범위로 나타날까요?</h3>
          <p className="caption">
            {simWaiting ? "시뮬레이션을 계산하고 있어요." : "결과는 판정 아래에 이어서 보여드려요."}
          </p>
          <Button disabled={simWaiting || !hasSim} onClick={() => setShowSim(true)}>
            {simWaiting ? "계산하고 있어요" : hasSim ? "가격 시나리오 보기" : "시나리오를 만들지 못했어요"}
          </Button>
        </section>
      )}

      {keyPoints.length ? (
        <section className="focus">
          <h3>먼저 확인할 것</h3>
          <p>온보딩 답변에 맞춰 {focus ?? "확인할 내용"}을 앞에 뒀어요. 결론은 성향과 관계없이 같아요.</p>
          {keyPoints.map((k) => (
            <strong key={k}>{k}</strong>
          ))}
        </section>
      ) : null}

      <h2 className="section-title">토론 내용</h2>
      <DebateChat
        agendas={agendas.map((a) => ({
          id: a.agenda_id,
          title: a.agenda_title,
          bull: a.bull,
          bear: a.bear,
          reasoning: a.verdict?.reasoning,
        }))}
      />

      <FeedbackCard jobId={job.job_id} />
      <AiNote />
      <Disclaimer />
    </div>
  );
}

function SimulationCard({ simulation }: { simulation: SimulationResult }) {
  const base = simulation.chart_data?.base;
  const stats = simulationStats(base, simulation.current_price);
  return (
    <section className="card sim">
      <h3>
        {stats ? `${stats.days}일 ` : ""}가격 범위{stats ? ` (${stats.lowName}~${stats.highName})` : ""}
      </h3>
      <SimulationChart paths={base} />
      {stats ? <p className="caption">오늘부터 {stats.days}일. 가운데 점선은 중앙값이에요.</p> : null}
      {stats ? (
        <dl>
          <div>
            <dt>
              {stats.lowName}~{stats.highName} 범위
            </dt>
            <dd>
              {stats.low} ~ {stats.high}
            </dd>
          </div>
          <div>
            <dt>하위 {stats.lowName.slice(1)}% 손실 기준</dt>
            <dd>{stats.low}</dd>
          </div>
        </dl>
      ) : null}
      {simulation.interpretation ? <p className="sim-text">{simulation.interpretation}</p> : null}
      <p className="sim-note">
        이 결과는 과거 데이터와 가정에 기반한 가상의 시나리오이며, 미래 수익률이나 가격을 예측·보장하지 않습니다.
      </p>
    </section>
  );
}

const feedbackReasons = ["사실 오류", "근거 없음", "오래된 정보", "이해 어려움"];

function FeedbackCard({ jobId }: { jobId: string }) {
  const [vote, setVote] = useState<"up" | "down">();
  const [reason, setReason] = useState<string>();
  const send = useMutation({
    mutationFn: (payload: { helpful: boolean; reason?: string }) => api.sendFeedback(jobId, payload),
  });
  return (
    <section className="card feedback">
      <h3>이 결과가 도움이 됐나요?</h3>
      <div className="vote">
        <button
          type="button"
          aria-pressed={vote === "up"}
          className={vote === "up" ? "selected" : ""}
          onClick={() => {
            setVote("up");
            setReason(undefined);
            send.mutate({ helpful: true });
          }}
        >
          <ThumbsUp size={24} aria-hidden /> 도움됨
        </button>
        <button
          type="button"
          aria-pressed={vote === "down"}
          className={vote === "down" ? "selected" : ""}
          onClick={() => {
            setVote("down");
            send.mutate({ helpful: false });
          }}
        >
          <ThumbsDown size={24} aria-hidden /> 아쉬움
        </button>
      </div>
      {vote === "down" ? (
        <div className="chips">
          {feedbackReasons.map((r) => (
            <Chip
              key={r}
              selected={reason === r}
              onClick={() => {
                setReason(r);
                send.mutate({ helpful: false, reason: r });
              }}
            >
              {r}
            </Chip>
          ))}
        </div>
      ) : null}
      {send.error ? <ErrorText>의견을 저장하지 못했어요.</ErrorText> : null}
    </section>
  );
}
