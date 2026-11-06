// `sends`는 backend/onboarding/processor.py의 매핑 키와 정확히 같아야 한다. 다르면 저장이 400으로 실패한다.
export type Question = {
  id: "goal" | "horizon" | "asset_share" | "loss_reaction" | "loss_limit" | "experience";
  field?: "q1" | "q2" | "q3_1" | "q4" | "q5";
  eyebrow?: string;
  title: string;
  sub?: string;
  tip?: string;
  options: Array<{ id: string; label: string; sends?: string }>;
};

export const questions: Question[] = [
  {
    id: "goal",
    field: "q2",
    eyebrow: "제가 가장 먼저 신경 쓸 일을 정해주세요.",
    title: "이번 투자에서\n가장 중요한 건 뭔가요?",
    options: [
      { id: "keep_principal", label: "넣은 돈을 지키는 거예요", sends: "넣은 돈이 그대로 있으면 돼요" },
      { id: "beat_deposit", label: "예금 이자보다 조금 더 벌면 돼요", sends: "은행 이자보다만 조금 더 벌면 돼요" },
      { id: "market_return", label: "시장 평균만큼 벌면 충분해요", sends: "시장 평균 수익률 정도면 충분해요" },
      { id: "high_return", label: "손실 위험이 커도 크게 벌고 싶어요", sends: "크게 벌고 싶어요. 리스크는 감수할게요" },
    ],
  },
  {
    id: "horizon",
    field: "q1",
    title: "이 돈은 언제쯤 다시 쓸 것 같아요?",
    sub: "전세금이나 등록금처럼 쓸 날이 정해진 돈이라면 그 날짜를 기준으로 골라주세요.",
    tip: "쓸 날이 가까운 돈은 가격이 회복될 시간이 짧을 수 있어요.",
    options: [
      { id: "within_6m", label: "6개월 안에 써요", sends: "6개월 안에 꺼낼 것 같아요" },
      { id: "from_6m_to_1y", label: "6개월~1년 사이에 써요", sends: "6개월 ~ 1년 사이에요" },
      { id: "from_1y_to_3y", label: "1~3년 뒤에 써요", sends: "1년 ~ 3년 정도 묻어둘게요" },
      { id: "over_3y", label: "3년 넘게 안 쓸 것 같아요", sends: "3년 이상 장기 투자할 거예요" },
    ],
  },
  {
    id: "asset_share",
    field: "q3_1",
    eyebrow: "예금, 주식, 펀드를 모두 합친 돈을 100이라고 해볼게요.",
    title: "이번 투자금은 얼마쯤 되나요?",
    tip: "비중이 클수록 같은 하락도 전체 자산에 더 크게 느껴져요.",
    options: [
      { id: "under_10", label: "10보다 적어요", sends: "10% 미만" },
      { id: "from_10_to_30", label: "10~30 정도예요", sends: "10% ~ 30% 정도예요" },
      { id: "from_30_to_50", label: "30~50 정도예요", sends: "30% ~ 50% 정도예요" },
      { id: "over_50", label: "50보다 많아요", sends: "50% 이상" },
    ],
  },
  {
    id: "loss_reaction",
    field: "q4",
    eyebrow: "100만 원어치 산 주식이 한 달 뒤 80만 원이 됐어요.",
    title: "어떻게 하실 것 같아요?",
    tip: "정답은 없어요. 하락했을 때 어떤 정보부터 챙길지 정하는 데 참고할게요.",
    options: [
      { id: "sell_all", label: "더 떨어질까 봐 다 팔 것 같아요", sends: "일단 다 팔고 본다. 더 떨어지면 못 버텨" },
      { id: "sell_part", label: "이유를 찾아보고 일부만 팔 것 같아요", sends: "왜 떨어진 건지 알아보고 일부만 판다" },
      { id: "hold", label: "이유를 찾아보고 그대로 둘 것 같아요", sends: "언젠간 오르겠지. 그냥 들고 기다린다" },
      { id: "buy_more", label: "이유를 찾아보고 더 살 것 같아요", sends: "오히려 기회다! 더 산다" },
    ],
  },
  {
    id: "loss_limit",
    eyebrow: "1,000만 원을 1년 동안 투자한다면,",
    title: "어디까지 떨어져도\n계속 들고 갈 수 있을 것 같아요?",
    options: [
      { id: "down_5", label: "950만 원까지 (-5%)" },
      { id: "down_10", label: "900만 원까지 (-10%)" },
      { id: "down_20", label: "800만 원까지 (-20%)" },
      { id: "down_30_plus", label: "700만 원 아래여도 괜찮아요 (-30% 이상)" },
    ],
  },
  {
    id: "experience",
    field: "q5",
    title: "지금까지 직접 해본 투자 중\n가장 가까운 걸 골라주세요.",
    options: [
      { id: "savings_only", label: "예금·적금까지 해봤어요", sends: "예·적금이 전부예요" },
      { id: "bonds_funds", label: "채권이나 펀드까지 해봤어요", sends: "채권·펀드 정도 해봤어요" },
      { id: "stocks", label: "주식을 직접 사고팔아 봤어요", sends: "주식 사고팔아 봤어요" },
      { id: "derivatives", label: "선물, 옵션, 레버리지 ETF도 해봤어요", sends: "선물·옵션·레버리지 ETF도 해봤어요" },
    ],
  },
];

export const sectors = [
  { code: "반도체_종합전자", label: "반도체·종합전자" },
  { code: "메모리_HBM", label: "메모리·HBM" },
  { code: "자동차", label: "자동차" },
  { code: "인터넷_플랫폼", label: "인터넷·플랫폼" },
  { code: "음식료", label: "음식료" },
  { code: "엔터테인먼트", label: "엔터테인먼트" },
  { code: "2차전지_배터리", label: "2차전지·배터리" },
];

export const sectorLabel = (code: string) => sectors.find((s) => s.code === code)?.label ?? code;

export const profiles: Record<string, { label: string; focus: string }> = {
  conservative: { label: "안정형", focus: "손실 가능성과 재무 위험, 공시 리스크" },
  moderate_conservative: { label: "안정추구형", focus: "손실 가능성과 실적 안정성" },
  moderate: { label: "위험중립형", focus: "손실 위험과 가격 변동" },
  aggressive: { label: "적극투자형", focus: "성장 근거와 변동성" },
  very_aggressive: { label: "공격투자형", focus: "성장 근거와 변동성, 최대 손실 구간" },
};

export type Answers = Partial<Record<Question["id"], string>> & {
  risk_return?: string;
  sectors?: string[];
  tickers?: string[];
};

// shortcut: 관심 종목 저장 API가 없어 브라우저에 둔다. interest_tickers API가 생기면 서버로 옮긴다.
export const tickersKey = "ant-secretariat-tickers";
export function readTickers(): string[] {
  try {
    return JSON.parse(localStorage.getItem(tickersKey) ?? "[]");
  } catch {
    return [];
  }
}

export function mismatchMessage(a: Answers) {
  if (a.loss_limit === "down_5" && (a.loss_reaction === "hold" || a.loss_reaction === "buy_more")) {
    return "앞에서 20% 하락에도 보유하거나 더 산다고 하셨는데, 지금은 5% 하락까지 괜찮다고 하셨어요. 다시 볼까요?";
  }
  if (a.loss_limit === "down_30_plus" && a.loss_reaction === "sell_all") {
    return "앞에서 20% 하락이면 모두 판다고 하셨는데, 지금은 30% 넘게 떨어져도 괜찮다고 하셨어요. 다시 볼까요?";
  }
  return null;
}

export function toPayload(userId: string, a: Answers) {
  const payload: Record<string, unknown> = { user_id: userId, q6: a.sectors ?? [] };
  for (const q of questions) {
    if (q.field) payload[q.field] = q.options.find((o) => o.id === a[q.id])?.sends;
  }
  return payload;
}
