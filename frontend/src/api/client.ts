import { mockApi } from "./mock";
import type {
  Company,
  DataStatus,
  DebateJob,
  InsightBoardResult,
  InsightFeature,
  TrendFeed,
  TrendReportResult,
  UserContext,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const ngrokBypassHeaders = API_BASE_URL.includes("ngrok-free")
  ? { "ngrok-skip-browser-warning": "true" }
  : {};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  Object.entries(ngrokBypassHeaders).forEach(([key, value]) => headers.set(key, value));

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      message = body.detail ?? message;
    } catch {
      // Keep the HTTP status message.
    }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }

  return response.json() as Promise<T>;
}

const realApi = {
  health: () => request<{ status: string }>("/health"),
  companies: async () => {
    const data = await request<{ companies: Company[] }>("/companies");
    return data.companies;
  },
  dataStatus: (ticker: string) => request<DataStatus>(`/companies/${ticker}/data-status`),
  createUser: (userId: string) =>
    request<{ user_id: string; created: boolean }>("/users", {
      method: "POST",
      body: JSON.stringify({ user_id: userId }),
    }),
  resetUser: (userId: string) =>
    request<{ user_id: string; deleted_jobs: number; deleted_user: boolean }>(`/users/${userId}/reset`, {
      method: "DELETE",
    }),
  saveOnboarding: (payload: Record<string, unknown>) =>
    request<Record<string, unknown>>("/onboarding", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  userContext: (userId: string) => request<UserContext>(`/users/${userId}/context`),
  insightBoard: (payload: {
    user_id: string;
    companies: string[];
    feature: InsightFeature;
    date_from?: string;
    date_to?: string;
  }) =>
    request<InsightBoardResult>("/orchestrate/insight-board", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  trendReport: async (payload: {
    company: string;
    query?: string;
    date_from?: string;
    date_to?: string;
  }) => {
    const data = await request<{ report: TrendReportResult }>("/agents/trend-report", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    return data.report;
  },
  startDebate: (payload: { user_id: string; company: string; query: string }) =>
    request<{
      job_id: string;
      status: string;
      request_type: string;
      ticker: string;
      company: string;
    }>("/orchestrate/debate", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  debateJob: async (jobId: string) => {
    const data = await request<{ job: DebateJob }>(`/debate/jobs/${jobId}`);
    return data.job;
  },
  userJobs: async (userId: string) => {
    const data = await request<{ jobs: DebateJob[] }>(`/users/${userId}/jobs`);
    return data.jobs;
  },
  sendFeedback: (jobId: string, payload: { helpful: boolean; reason?: string }) =>
    request<Record<string, unknown>>(`/debate/jobs/${jobId}/feedback`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  // shortcut: 사전 생성 API가 없어 빈 값을 준다. 일일 사전 생성이 생기면 서버 값으로 바꾼다.
  trendFeed: async (_userId: string): Promise<TrendFeed> => ({ cards: {}, changes: [] }),
};

// 화면 점검용. VITE_USE_MOCK=true일 때만 예시 데이터를 쓴다.
export const api: typeof realApi = import.meta.env.VITE_USE_MOCK === "true" ? mockApi : realApi;

export { API_BASE_URL };
