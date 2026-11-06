import type { DebateJob } from "../types";

/** DebateStepper 단계: 자료 0, 찬성 1, 반대 2, 판정 3, 완료 4(끝나면 5). */
export function debateStep(job: Pick<DebateJob, "status" | "partial_result">) {
  if (job.status === "completed" || job.status === "debate_completed" || job.status === "simulation_running") return 5;
  const stage = job.partial_result?.stage;
  if (stage === "judge_completed") return 4;
  if (stage === "bear_completed") return 3;
  if (stage === "bull_completed") return 2;
  if (stage === "data_collected") return 1;
  return 0;
}

export const stepHeadline = [
  "자료를 모으고 있어요",
  "찬성 측이 근거를\n찾고 있어요",
  "반대 측이 위험 요인을\n찾고 있어요",
  "양쪽 근거를\n판정하고 있어요",
  "결과를 정리하고 있어요",
];

export const stepBanner = [
  "자료를 모으고 있어요",
  "찬성 측이 근거를 찾고 있어요",
  "반대 측이 위험 요인을 찾고 있어요",
  "양쪽 근거를 판정하고 있어요",
  "결과를 정리하고 있어요",
];

export const isRunning = (job: DebateJob) => job.status === "queued" || job.status === "running";

export function formatJobTime(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const time = d.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit" });
  const today = new Date().toDateString() === d.toDateString();
  return today ? `오늘 ${time}` : `${d.getMonth() + 1}월 ${d.getDate()}일 ${time}`;
}

export function formatDay(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : `${d.getMonth() + 1}월 ${d.getDate()}일`;
}

/** 범위 밖 질문(추천, 매매 시점, 단기 예측)을 서버로 보내기 전에 거른다. */
const outOfScope = /(살까|팔까|사도\s*돼|팔아도\s*돼|매수|매도|추천|얼마.*(투자|넣)|(내일|다음\s*주|이번\s*주).*(오를|내릴|떨어|주가)|단타)/;
export const isOutOfScope = (text: string) => outOfScope.test(text);
