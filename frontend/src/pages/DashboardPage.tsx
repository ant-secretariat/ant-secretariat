import { useQueries, useQuery } from "@tanstack/react-query";
import { ChevronRight, FileText, Scale } from "lucide-react";
import { Link, Navigate } from "react-router-dom";
import { api } from "../api/client";
import { Ant, Badge, Disclaimer, ErrorText, ListRow, Skeleton, TopBar } from "../components/ui";
import { readTickers } from "../data/onboarding";
import { debateStep, formatDay, isRunning, stepBanner } from "../lib/debate";
import { useAppStore } from "../store/appStore";

export function DashboardPage() {
  const userId = useAppStore((state) => state.userId) ?? "";
  const context = useQuery({
    queryKey: ["user-context", userId],
    queryFn: () => api.userContext(userId),
    retry: false,
  });
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const jobs = useQuery({ queryKey: ["user-jobs", userId], queryFn: () => api.userJobs(userId) });

  const sectors = context.data?.interest_sectors ?? [];
  const tickers = readTickers();
  const all = companies.data ?? [];
  const interest = [
    ...all.filter((c) => tickers.includes(c.ticker)),
    ...all.filter((c) => !tickers.includes(c.ticker) && sectors.includes(c.sector)),
  ].slice(0, 3);
  const insights = useQueries({
    queries: interest.map((c) => ({
      queryKey: ["insight-board", userId, c.company],
      queryFn: () => api.insightBoard({ user_id: userId, companies: [c.company], feature: "price" as const }),
      staleTime: 5 * 60_000,
    })),
  });

  const running = jobs.data?.find(isRunning);
  const recent = (jobs.data ?? []).filter((j) => j.status === "completed").slice(0, 2);

  if (context.error || context.data?.onboarding_done === false) return <Navigate to="/onboarding" replace />;

  if (context.isLoading) {
    return (
      <div className="screen">
        <TopBar title="개미비서단" settings />
        <Skeleton />
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar title="개미비서단" settings />
      {running ? (
        <Link className="banner" to={`/debate/${running.job_id}`}>
          <span>
            <strong>
              {running.company} 토론 진행 중 ({Math.min(debateStep(running) + 1, 5)}/5)
            </strong>
            <span>{stepBanner[debateStep(running)] ?? "결과를 정리하고 있어요"}</span>
          </span>
          <ChevronRight size={24} aria-hidden />
        </Link>
      ) : null}

      <div className="hero-row">
        <Ant kind="chart" size={84} />
        <h2 className="display">
          오늘 관심 종목에
          <br />
          이런 소식이 있어요
        </h2>
      </div>

      <section className="card insight">
        {!interest.length && !context.isLoading && !companies.isLoading ? (
          <p className="caption">관심 산업의 종목을 찾지 못했어요. 설정에서 관심 산업을 확인해 주세요.</p>
        ) : null}
        {context.isLoading || companies.isLoading ? <Skeleton /> : null}
        {interest.map((c, i) => {
          const q = insights[i];
          return (
            <article key={c.ticker}>
              <h3>{c.company}</h3>
              {q?.isLoading ? <Skeleton /> : null}
              {q?.error ? <ErrorText>소식을 불러오지 못했어요.</ErrorText> : null}
              {q?.data ? (
                <>
                  <div className="badges">
                    {q.data.badges.map((b) => (
                      <PriceBadge key={b} text={b} />
                    ))}
                  </div>
                  <p className="caption">{q.data.llm_comment}</p>
                </>
              ) : null}
            </article>
          );
        })}
      </section>

      <h2 className="section-title">무엇을 해볼까요</h2>
      <Link className="action-card" to="/trend-report">
        <FileText size={24} aria-hidden />
        <span>
          <strong>트렌드 리포트 보기</strong>
          <span>관심 종목과 산업 소식을 카드뉴스로 봐요.</span>
          <em>약 10초 걸리고, 다시 볼 수 있어요.</em>
        </span>
        <ChevronRight size={24} aria-hidden />
      </Link>
      <Link className="action-card" to="/debate">
        <Scale size={24} aria-hidden />
        <span>
          <strong>찬반 토론 시작</strong>
          <span>한 종목의 찬성과 반대 근거를 나란히 봐요.</span>
          <em>약 2~3분 걸리고, 이력에 저장돼요.</em>
        </span>
        <ChevronRight size={24} aria-hidden />
      </Link>

      {recent.length ? (
        <>
          <h2 className="section-title">최근 분석</h2>
          <div className="card list">
            {recent.map((j) => (
              <ListRow
                key={j.job_id}
                title={`${j.company} 토론`}
                sub={`완료, ${formatDay(j.updated_at)}`}
                to={`/debate/${j.job_id}`}
              />
            ))}
          </div>
        </>
      ) : null}
      <Disclaimer />
    </div>
  );
}

function PriceBadge({ text }: { text: string }) {
  if (/^\+/.test(text)) return <Badge tone="up">▲ {text}</Badge>;
  if (/^-/.test(text)) return <Badge tone="down">▼ {text}</Badge>;
  return <Badge>{text}</Badge>;
}
