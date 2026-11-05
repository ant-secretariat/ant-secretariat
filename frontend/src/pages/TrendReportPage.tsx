import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { api } from "../api/client";
import {
  AiNote,
  Badge,
  Button,
  Disclaimer,
  EmptyView,
  ErrorText,
  ListRow,
  Sheet,
  Skeleton,
  TopBar,
} from "../components/ui";
import { sectorLabel } from "../data/onboarding";
import { formatDay } from "../lib/debate";
import { useAppStore } from "../store/appStore";
import type { TrendReportResult } from "../types";

const lastViewedKey = "ant-secretariat-last-report";

export function TrendReportPage() {
  const userId = useAppStore((state) => state.userId) ?? "";
  const [text, setText] = useState("");
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const context = useQuery({
    queryKey: ["user-context", userId],
    queryFn: () => api.userContext(userId),
    retry: false,
  });
  const feed = useQuery({ queryKey: ["trend-feed", userId], queryFn: () => api.trendFeed(userId) });

  const all = companies.data ?? [];
  const sectors = context.data?.interest_sectors ?? [];
  const interest = all.filter((c) => sectors.includes(c.sector));
  const others = all.filter((c) => !sectors.includes(c.sector)).slice(0, 2);
  const matches = text ? all.filter((c) => c.company.includes(text)).slice(0, 5) : [];
  const last = readLastViewed();

  return (
    <div className="screen">
      <TopBar title="트렌드 리포트" settings />
      <div className="field">
        <label htmlFor="company">다른 종목 찾기</label>
        <input id="company" value={text} placeholder="종목명으로 찾기" onChange={(e) => setText(e.target.value)} />
        <p className="helper">분석 준비 중인 종목도 함께 보여드려요.</p>
      </div>
      {matches.length ? (
        <div className="card list">
          {matches.map((c) => (
            <ListRow key={c.ticker} title={c.company} sub={sectorLabel(c.sector)} to={`/trend-report/${c.ticker}`} />
          ))}
        </div>
      ) : null}
      {text && !matches.length && !companies.isLoading ? <p className="caption">찾는 종목이 없어요.</p> : null}

      {last ? (
        <>
          <h2 className="section-title">이어보기</h2>
          <div className="card list">
            <ListRow title={last.company} sub="최근에 본 리포트" to={`/trend-report/${last.ticker}`} />
          </div>
        </>
      ) : null}

      <h2 className="section-title">내 관심 종목과 산업</h2>
      {companies.isLoading || context.isLoading ? <Skeleton /> : null}
      <div className="carousel">
        {interest.map((c) => {
          const card = feed.data?.cards[c.ticker];
          return (
            <Link className="trend-card" key={c.ticker} to={`/trend-report/${c.ticker}`}>
              <span className="trend-sector">{sectorLabel(c.sector)}</span>
              <strong>{card?.title ?? `${c.company} 소식을 정리해 드려요`}</strong>
              <span className="trend-meta">{card?.meta ?? "약 10초 걸려요"}</span>
            </Link>
          );
        })}
      </div>

      {feed.data?.changes.length ? (
        <>
          <h2 className="section-title">오늘 달라진 것</h2>
          <div className="card list">
            {feed.data.changes.map((c) => (
              <ListRow key={c.ticker} title={c.company} sub={c.text} to={`/trend-report/${c.ticker}`} />
            ))}
          </div>
        </>
      ) : null}

      {others.length ? (
        <>
          <h2 className="section-title">이런 종목도 있어요</h2>
          <div className="card list">
            {others.map((c) => (
              <ListRow key={c.ticker} title={c.company} sub={sectorLabel(c.sector)} to={`/trend-report/${c.ticker}`} />
            ))}
          </div>
        </>
      ) : null}
      <Disclaimer />
    </div>
  );
}

function readLastViewed(): { ticker: string; company: string } | null {
  try {
    return JSON.parse(localStorage.getItem(lastViewedKey) ?? "null");
  } catch {
    return null;
  }
}

export function TrendReportDetailPage() {
  const { ticker = "" } = useParams();
  const navigate = useNavigate();
  const companies = useQuery({ queryKey: ["companies"], queryFn: api.companies });
  const company = companies.data?.find((c) => c.ticker === ticker);
  const report = useQuery({
    queryKey: ["trend-report", ticker],
    enabled: Boolean(company),
    staleTime: 10 * 60_000,
    retry: false,
    queryFn: async () => {
      const data = await api.trendReport({ company: company!.company });
      try {
        localStorage.setItem(lastViewedKey, JSON.stringify({ ticker, company: company!.company }));
      } catch {
        // 이어보기만 안 될 뿐이다.
      }
      return data;
    },
  });

  const title = company ? `${company.company} 리포트` : "리포트";
  const cards = report.data?.cards;
  const empty =
    report.data && !cards?.summary?.length && !cards?.positive_factors?.length && !cards?.risk_factors?.length;

  if (empty) {
    return (
      <div className="screen fill">
        <TopBar title="리포트" back="/trend-report" />
        <EmptyView
          title={
            <>
              아직 이 종목의 리포트를
              <br />
              모으지 못했습니다.
            </>
          }
          body="수집은 매일 아침 갱신됩니다."
        />
        <Button variant="secondary" className="foot-btn" onClick={() => navigate("/trend-report")}>
          다른 종목 찾기
        </Button>
      </div>
    );
  }

  return (
    <div className="screen">
      <TopBar title={title} back="/trend-report" />
      {report.isLoading || companies.isLoading ? (
        <>
          <p className="caption">리포트를 정리하고 있어요. 약 10초 걸려요.</p>
          <Skeleton />
        </>
      ) : null}
      {report.error ? (
        <>
          <ErrorText>리포트를 불러오지 못했어요.</ErrorText>
          <Button variant="secondary" onClick={() => report.refetch()}>
            다시 시도
          </Button>
        </>
      ) : null}
      {report.data ? <ReportBody report={report.data} /> : null}
      <Disclaimer />
    </div>
  );
}

type Row = Record<string, unknown>;
const clean = (v: unknown) => String(v ?? "").replace(/\s*\[S\d+(,\s*S\d+)*\]/g, "").trim();

function ReportBody({ report }: { report: TrendReportResult }) {
  const [sheet, setSheet] = useState<{ title: string; refs?: string[] } | null>(null);
  const c = report.cards;
  const target = c.target_price_trend ?? {};
  const series = Array.isArray(target.series) ? (target.series as number[]) : [];
  const refsOf = (items?: Row[]) => [...new Set((items ?? []).flatMap((i) => (i.evidence as string[]) ?? []))];
  const textRefs = (lines?: string[]) => [
    ...new Set((lines ?? []).flatMap((l) => l.match(/S\d+/g) ?? [])),
  ];
  const line = (items?: Row[]) =>
    (items ?? []).map((i) => clean(i.description ?? i.view ?? i.title)).filter(Boolean);

  return (
    <>
      <div className="badges head">
        {report.as_of_date ? <Badge>{formatDay(report.as_of_date)} 기준</Badge> : null}
        <Badge>근거 {report.evidence.length}건</Badge>
      </div>
      <ReportCard
        title="요약"
        lines={(c.summary ?? []).map(clean)}
        count={textRefs(c.summary).length || report.evidence.length}
        onOpen={() => setSheet({ title: "요약", refs: textRefs(c.summary) })}
      />
      <ReportCard
        title="긍정 요인"
        lines={line(c.positive_factors)}
        count={refsOf(c.positive_factors).length}
        onOpen={() => setSheet({ title: "긍정 요인", refs: refsOf(c.positive_factors) })}
      />
      <ReportCard
        title="리스크 요인"
        lines={line(c.risk_factors)}
        count={refsOf(c.risk_factors).length}
        onOpen={() => setSheet({ title: "리스크 요인", refs: refsOf(c.risk_factors) })}
      />
      <ReportCard
        title="증권사 시각차"
        lines={(c.broker_differences ?? []).map((b) => `${clean(b.broker)}: ${clean(b.view)}`)}
        count={0}
      />
      {target.comment ? (
        <ReportCard title="목표주가 추이" lines={[clean(target.comment)]} count={0}>
          {series.length > 1 ? <TargetLine values={series} /> : null}
        </ReportCard>
      ) : null}
      <ReportCard
        title="뉴스 이슈"
        lines={line(c.news_issue_cards)}
        count={refsOf(c.news_issue_cards).length}
        onOpen={() => setSheet({ title: "뉴스 이슈", refs: refsOf(c.news_issue_cards) })}
      />
      <AiNote />
      {sheet ? <EvidenceSheet report={report} title={sheet.title} refs={sheet.refs} onClose={() => setSheet(null)} /> : null}
    </>
  );
}

function ReportCard({
  title,
  lines,
  count,
  onOpen,
  children,
}: {
  title: string;
  lines: string[];
  count: number;
  onOpen?: () => void;
  children?: React.ReactNode;
}) {
  if (!lines.length) return null;
  return (
    <section className="card report">
      <h2>{title}</h2>
      {lines.map((l) => (
        <p key={l}>{l}</p>
      ))}
      {children}
      {count > 0 && onOpen ? (
        <button type="button" className="link" onClick={onOpen}>
          근거 {count}건 보기
        </button>
      ) : null}
    </section>
  );
}

function EvidenceSheet({
  report,
  title,
  refs,
  onClose,
}: {
  report: TrendReportResult;
  title: string;
  refs?: string[];
  onClose: () => void;
}) {
  const items = report.evidence.filter((e) => refs?.includes(String(e.evidence_id)));
  const url = items.map((e) => e.url).find((u): u is string => typeof u === "string" && u.startsWith("http"));
  return (
    <Sheet title={`${title}의 근거 ${items.length}건`} onClose={onClose}>
      <div className="evidence-list">
        {items.slice(0, 5).map((e) => (
          <article key={String(e.evidence_id)}>
            <h3>{clean(e.title)}</h3>
            <span>
              {clean(e.author_org ?? e.source)}
              {e.date ? `, ${clean(e.date)}` : ""}
            </span>
            {e.content ? <p>{clean(e.content).slice(0, 80)}</p> : null}
          </article>
        ))}
      </div>
      {url ? (
        <a className="btn btn-text" href={url} target="_blank" rel="noreferrer">
          원문 열기
        </a>
      ) : null}
      <Button variant="text" onClick={onClose}>
        닫기
      </Button>
    </Sheet>
  );
}

function TargetLine({ values }: { values: number[] }) {
  const w = 300;
  const h = 70;
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const points = values.map((v, i) => [8 + (i / (values.length - 1)) * (w - 16), h - 12 - ((v - min) / span) * (h - 24)]);
  return (
    <svg className="target-line" viewBox={`0 0 ${w} ${h + 10}`} role="img" aria-label="목표주가 추이">
      <polyline points={points.map((p) => p.join(",")).join(" ")} />
      {points.map(([x, y]) => (
        <circle key={x} cx={x} cy={y} r="5" />
      ))}
      <line x1="0" x2={w} y1={h + 8} y2={h + 8} />
    </svg>
  );
}
