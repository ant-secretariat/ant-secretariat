export type Company = {
  ticker: string;
  company: string;
  sector: string;
  aliases?: string[];
};

export type DataStatus = {
  ticker: string;
  company: string;
  available: Record<string, boolean>;
  latest: Record<string, string | null>;
};

export type InsightFeature = "price" | "macro" | "disclosure";

export type InsightBoardResult = {
  raw_data: unknown;
  llm_comment: string;
  badges: string[];
};

export type TrendReportResult = {
  ticker: string;
  company: string;
  as_of_date: string;
  cards: {
    summary?: string[];
    positive_factors?: Array<Record<string, unknown>>;
    risk_factors?: Array<Record<string, unknown>>;
    broker_differences?: Array<Record<string, unknown>>;
    target_price_trend?: Record<string, unknown>;
    news_issue_cards?: Array<Record<string, unknown>>;
    macro_comment?: string;
    [key: string]: unknown;
  };
  evidence: Array<Record<string, unknown>>;
  data_status: Record<string, unknown>;
};

export type JobStatus =
  | "queued"
  | "running"
  | "debate_completed"
  | "simulation_running"
  | "completed"
  | "failed";

export type DebateJob = {
  job_id: string;
  user_id: string;
  job_type: "debate";
  ticker: string;
  company: string;
  sector: string;
  status: JobStatus;
  error_message: string;
  created_at: string;
  updated_at: string;
  request: Record<string, unknown>;
  partial_result?: DebatePartialResult;
  debate_result?: DebateResult;
  simulation_result?: SimulationResult | Record<string, never>;
};

export type DebatePartialResult = {
  stage?: string;
  ticker?: string;
  company?: string;
  query?: string;
  data_richness?: string;
  bull_output?: {
    agendas?: Array<{
      agenda_id?: number;
      agenda_title?: string;
      arguments?: DebateArgument[];
      summary?: string;
    }>;
    overall_summary?: string;
  };
  bear_output?: {
    agendas?: Array<{
      agenda_id?: number;
      agenda_title?: string;
      arguments?: DebateArgument[];
      summary?: string;
      bull_claim?: string;
    }>;
    overall_summary?: string;
  };
  judge_output?: {
    agenda_verdicts?: Array<{
      agenda_id?: number;
      agenda_title?: string;
      winner?: string;
      reasoning?: string;
      key_point?: string;
    }>;
    overall_verdict?: Record<string, unknown>;
  };
  updated_at?: string;
};

export type DebateResult = {
  debate_result?: {
    meta: {
      ticker: string;
      company: string;
      query: string;
      user_id: string;
      timestamp: string;
      data_richness: string;
    };
    agendas: DebateAgenda[];
    judge: {
      user_profile: Record<string, unknown>;
      overall_verdict: Record<string, unknown>;
    };
  };
};

export type DebateAgenda = {
  agenda_id: number;
  agenda_title: string;
  bull: {
    arguments: DebateArgument[];
    summary: string;
  };
  bear: {
    arguments: DebateArgument[];
    summary: string;
  };
  verdict: {
    winner: string;
    reasoning: string;
    key_point: string;
  };
};

export type DebateArgument = {
  title?: string;
  content?: string;
  source?: string;
  source_title?: string;
  source_date?: string;
  confidence?: number;
  rebuttal_target?: string;
};

export type SimulationResult = {
  ticker?: string;
  current_price?: number;
  simulation_type?: string;
  summary?: {
    expected_return_pct: number;
    upside_probability: number;
    volatility: number;
  };
  scenarios?: Record<string, unknown>;
  chart_data?: {
    base?: PercentilePath;
    what_if?: Array<{
      variable: string;
      direction: string;
      paths: PercentilePath;
    }>;
  };
  interpretation?: string;
  risk_card?: {
    volatility?: number;
    pessimistic_return_pct?: number;
    quantified_risks?: Array<{
      variable: string;
      direction: string;
      impact_pct: number;
    }>;
    tone?: string;
  };
  user_profile?: Record<string, unknown>;
  error?: string;
  message?: string;
};

export type PercentilePath = {
  p10?: number[];
  p50?: number[];
  p90?: number[];
  [key: string]: number[] | undefined;
};

export type UserContext = {
  user_id: string;
  risk_profile: string;
  investment_goal: string;
  investment_amount_range: string;
  investment_experience: string;
  interest_sectors: string[];
  onboarding_done: boolean;
};
