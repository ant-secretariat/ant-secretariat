// 화면 점검 전용 예시 데이터. 실제 수치나 실제 증권사 의견이 아니다.
import type { Company, DataStatus, DebateJob, InsightBoardResult, TrendFeed, TrendReportResult, UserContext } from "../types";

const companies: Company[] = [
  { ticker: "000660", company: "SK하이닉스", sector: "메모리_HBM" },
  { ticker: "005930", company: "삼성전자", sector: "메모리_HBM" },
  { ticker: "035420", company: "NAVER", sector: "인터넷_플랫폼" },
  { ticker: "035720", company: "카카오", sector: "인터넷_플랫폼" },
  { ticker: "097950", company: "CJ제일제당", sector: "음식료" },
];

const path = (start: number, end: number, n = 31) =>
  Array.from({ length: n }, (_, i) => start + ((end - start) * i) / (n - 1));

const argument = (title: string, content: string, source: string, date: string, confidence: number, relation?: { title: string; body: string }) => ({
  title,
  content,
  source_title: source,
  source_date: date,
  confidence,
  relation_evidence: relation ? [relation] : undefined,
});

const debateResult = {
  debate_result: {
    meta: { ticker: "005930", company: "삼성전자", query: "", user_id: "mock", timestamp: "", data_richness: "" },
    judge: {
      user_profile: {},
      overall_verdict: {
        final_brief:
          "양쪽 근거가 비슷해요. 회복 속도를 더 확인해 보세요. 메모리 가격 회복은 양쪽 모두 인정해요. 쟁점은 수요가 언제 돌아오는지예요.",
      },
    },
    agendas: [
      {
        agenda_id: 1,
        agenda_title: "거시 환경",
        bull: {
          summary: "",
          arguments: [
            argument("환율 상승이 수출 실적에 도움이 돼요", "원화 약세 구간에서 영업이익이 늘어난 사례가 많아요.", "A증권 리포트", "2026-11-04", 0.6, {
              title: "환율 민감도",
              body: "삼성전자는 최근 3년 환율 변화와 양의 상관을 보였어요. 관계: 종목-매크로 민감도 / 값: +0.32 / 출처: 한국은행 환율, 시세 / 방법: 상관 기반 민감도 / 기준일: 2026-11-05",
            }),
          ],
        },
        bear: {
          summary: "",
          arguments: [
            argument("환율 효과는 원가 상승으로 줄어들 수 있어요", "수입 장비와 소재 비용도 함께 오르는 구간이에요.", "B증권 리포트", "2026-11-02", 0.6, {
              title: "원가 영향",
              body: "장비 수입 비중이 높은 구간에는 환율 상승이 원가에 먼저 반영될 수 있어요.",
            }),
          ],
        },
        verdict: { winner: "neutral", reasoning: "영향의 크기를 단정하기 어려워요. 환율과 원가를 함께 봐야 해요.", key_point: "다음 분기 메모리 가격 흐름" },
      },
      {
        agenda_id: 2,
        agenda_title: "위험 요인",
        bull: {
          summary: "",
          arguments: [argument("재고 조정이 거의 끝났어요", "고객사 재고가 낮아졌다는 자료가 늘고 있어요.", "C증권 리포트", "2026-11-01", 0.8)],
        },
        bear: {
          summary: "",
          arguments: [argument("스마트폰 수요 회복이 늦어요", "완성품 수요가 약하면 메모리 회복도 늦어질 수 있어요.", "D증권 리포트", "2026-10-30", 0.6)],
        },
        verdict: { winner: "neutral", reasoning: "단기 수요 지표가 더 필요해요.", key_point: "환율이 실적에 주는 영향" },
      },
    ],
  },
};

const job = (over: Partial<DebateJob>): DebateJob => ({
  job_id: "mock-done",
  user_id: "mock",
  job_type: "debate",
  ticker: "005930",
  company: "삼성전자",
  sector: "메모리_HBM",
  status: "completed",
  error_message: "",
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  request: { query: "최근 쟁점" },
  ...over,
});

const simulation = {
  current_price: 100,
  chart_data: { base: { p5: path(100, 86), p10: path(100, 91), p50: path(100, 101), p90: path(100, 112), p95: path(100, 117) } },
  interpretation:
    "반영한 위험 변수: 환율, 메모리 가격. 환율 시나리오는 구간이 0을 포함해 방향이 불확실해요.",
};

const running = job({
  job_id: "mock-running",
  status: "running",
  created_at: new Date(Date.now() - 72_000).toISOString(),
  partial_result: {
    stage: "bull_completed",
    bull_output: {
      overall_summary: "메모리 가격 회복이 실적을 끌어올릴 수 있다고 봐요.",
      agendas: [{ arguments: [{ source_title: "A증권 리포트", source_date: "2026-11-04" }] }],
    },
  },
});

const jobs: DebateJob[] = [
  running,
  job({
    job_id: "mock-done",
    company: "SK하이닉스",
    ticker: "000660",
    debate_result: debateResult,
    simulation_result: simulation,
    created_at: "2026-11-04T21:15:00+09:00",
    updated_at: "2026-11-04T21:18:00+09:00",
  }),
  job({ job_id: "mock-presim", company: "NAVER", ticker: "035420", status: "debate_completed", debate_result: debateResult, created_at: "2026-11-03T19:02:00+09:00" }),
  job({ job_id: "mock-failed", company: "카카오", ticker: "035720", status: "failed", created_at: "2026-11-01T08:30:00+09:00" }),
];

const report: TrendReportResult = {
  ticker: "005930",
  company: "삼성전자",
  as_of_date: "2026-11-05",
  data_status: {},
  evidence: [
    { evidence_id: "S1", title: "메모리 업황 점검", author_org: "A증권", date: "2026-11-04", content: "메모리 가격은 재고 조정을 거치며 회복 구간에 들어섰다는 판단입니다.", url: "https://example.com/a" },
    { evidence_id: "S2", title: "반도체 4분기 전망", author_org: "B증권", date: "2026-11-02", content: "회복 시점은 고객사 재고 소진 속도에 달려 있다고 봅니다." },
    { evidence_id: "S3", title: "메모리 수요 점검", author_org: "C증권", date: "2026-11-01", content: "고대역폭 메모리 주문이 늘고 있습니다." },
  ],
  cards: {
    summary: ["증권사들은 메모리 가격 회복을 공통으로 보고 있어요. 다만 회복 속도는 의견이 갈려요. [S1, S2]"],
    positive_factors: [{ title: "주문 증가", description: "고대역폭 메모리 주문이 늘고 있다는 분석이 많아요. [S3]", evidence: ["S3"] }],
    risk_factors: [{ title: "수요", description: "스마트폰 수요가 예상보다 약하면 회복이 늦어질 수 있어요. [S2]", evidence: ["S2"] }],
    broker_differences: [{ broker: "A증권", view: "내년 상반기 회복을 전망해요." }, { broker: "B증권", view: "하반기 회복을 전망해요." }],
    target_price_trend: { comment: "최근 3개월 동안 리포트 4건 중 3건이 목표주가를 올렸어요.", series: [10, 12, 16, 19] },
    news_issue_cards: [{ title: "투자", description: "신규 공장 투자 계획이 여러 매체에 보도됐어요. [S1]", evidence: ["S1"] }],
  },
};

let saved = false;
const wait = <T,>(value: T) => new Promise<T>((resolve) => setTimeout(() => resolve(value), 60));

export const mockApi = {
  health: () => wait({ status: "ok" }),
  companies: () => wait(companies),
  dataStatus: (ticker: string): Promise<DataStatus> =>
    wait({ ticker, company: "", available: { reports: ticker !== "035720" }, latest: {} }),
  createUser: (userId: string) => wait({ user_id: userId, created: true }),
  resetUser: (userId: string) => (saved = false, wait)({ user_id: userId, deleted_jobs: jobs.length, deleted_user: true }),
  saveOnboarding: (_payload: Record<string, unknown>): Promise<Record<string, unknown>> => {
    saved = true;
    return wait({ risk_profile: "moderate" });
  },
  userContext: (userId: string): Promise<UserContext> =>
    wait({
      user_id: userId,
      risk_profile: "moderate",
      investment_goal: "mid_term",
      investment_amount_range: "",
      investment_experience: "beginner",
      interest_sectors: ["메모리_HBM", "인터넷_플랫폼"],
      onboarding_done: userId === "mock" || saved, // 새 사용자는 온보딩부터 시작한다.
    }),
  insightBoard: (payload: { companies: string[] }): Promise<InsightBoardResult> =>
    wait(
      payload.companies[0] === "NAVER"
        ? { raw_data: null, badges: ["-0.8%", "공시 2건"], llm_comment: "오늘 새 공시가 올라왔어요. 내용을 먼저 확인해 보세요." }
        : { raw_data: null, badges: ["+1.2%", "공시 1건", "환율 변동"], llm_comment: "실적 발표 전후로 가격 움직임이 커졌어요." },
    ),
  trendReport: (payload: { company: string }) =>
    wait(payload.company === "카카오" ? { ...report, company: "카카오", cards: {}, evidence: [] } : { ...report, company: payload.company }),
  startDebate: (payload: { company: string }) =>
    wait({ job_id: "mock-running", status: "queued", request_type: "debate", ticker: "", company: payload.company }),
  debateJob: (jobId: string) => {
    const found = jobs.find((j) => j.job_id === jobId);
    return found ? wait(found) : Promise.reject(new Error("not found"));
  },
  userJobs: (_userId: string) => wait(jobs),
  sendFeedback: (_jobId: string, _payload: { helpful: boolean; reason?: string }): Promise<Record<string, unknown>> => wait({}),
  trendFeed: (_userId: string): Promise<TrendFeed> =>
    wait({
      cards: {
        "000660": { title: "HBM 공급 소식을 정리했어요", meta: "11월 5일 기준, 근거 8건" },
        "035420": { title: "광고 실적 전망이 달라졌어요", meta: "11월 5일 기준, 근거 5건" },
      },
      changes: [
        { ticker: "005930", company: "삼성전자", text: "오늘 새 리포트 2건이 나왔어요." },
        { ticker: "000660", company: "SK하이닉스", text: "증권사 1곳이 목표주가를 바꿨어요." },
        { ticker: "035420", company: "NAVER", text: "증권사마다 보는 시각차가 커요." },
      ],
    }),
};
