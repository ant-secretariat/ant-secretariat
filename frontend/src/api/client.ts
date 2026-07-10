import type {
  Company,
  DataStatus,
  DebateJob,
  InsightBoardResult,
  InsightFeature,
  TrendReportResult,
  UserContext,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
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

export const api = {
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
};

export { API_BASE_URL };
