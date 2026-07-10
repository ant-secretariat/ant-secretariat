PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS report_metadata (
    report_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    author_org TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT 'unknown',
    original_url TEXT NOT NULL DEFAULT '',
    pdf_url TEXT,
    file_path TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('discovered', 'success', 'failed', 'duplicate', 'no_pdf_url')
    ),
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_report_metadata_pdf_url ON report_metadata(pdf_url);
CREATE INDEX IF NOT EXISTS idx_report_metadata_ticker ON report_metadata(ticker);
CREATE INDEX IF NOT EXISTS idx_report_metadata_published_at ON report_metadata(published_at);
CREATE INDEX IF NOT EXISTS idx_report_metadata_status ON report_metadata(status);

CREATE TABLE IF NOT EXISTS report_files (
    file_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    pdf_url TEXT,
    file_path TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    file_size INTEGER NOT NULL DEFAULT 0,
    content_type TEXT NOT NULL DEFAULT '',
    is_valid_pdf INTEGER NOT NULL DEFAULT 0,
    downloaded_at TEXT NOT NULL,
    status TEXT NOT NULL,
    error_message TEXT NOT NULL DEFAULT '',
    FOREIGN KEY(report_id) REFERENCES report_metadata(report_id)
);

CREATE INDEX IF NOT EXISTS idx_report_files_pdf_url ON report_files(pdf_url);
CREATE INDEX IF NOT EXISTS idx_report_files_sha256 ON report_files(sha256);

CREATE TABLE IF NOT EXISTS target_price_data (
    target_price_id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL,
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    target_price REAL,
    investment_opinion TEXT,
    source TEXT NOT NULL DEFAULT '',
    author_org TEXT NOT NULL DEFAULT '',
    report_type TEXT NOT NULL DEFAULT 'unknown',
    created_at TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES report_metadata(report_id)
);

CREATE TABLE IF NOT EXISTS price_data (
    ticker TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    price_date TEXT NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume INTEGER,
    market_cap REAL,
    volatility_30d REAL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (ticker, price_date, source)
);

CREATE TABLE IF NOT EXISTS macro_data (
    indicator_id TEXT NOT NULL,
    indicator_name TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL,
    value REAL,
    unit TEXT NOT NULL DEFAULT '',
    frequency TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (indicator_id, date, source)
);

CREATE TABLE IF NOT EXISTS news_metadata (
    news_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    original_url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_metadata_ticker ON news_metadata(ticker);
CREATE INDEX IF NOT EXISTS idx_news_metadata_published_at ON news_metadata(published_at);

CREATE TABLE IF NOT EXISTS disclosure_metadata (
    disclosure_id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    corp_code TEXT NOT NULL DEFAULT '',
    report_name TEXT NOT NULL DEFAULT '',
    disclosure_type TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    disclosed_at TEXT NOT NULL DEFAULT '',
    receipt_no TEXT NOT NULL DEFAULT '',
    original_url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_disclosure_metadata_ticker ON disclosure_metadata(ticker);
CREATE INDEX IF NOT EXISTS idx_disclosure_metadata_disclosed_at ON disclosure_metadata(disclosed_at);

CREATE TABLE IF NOT EXISTS report_chunk_records (
    chunk_id        TEXT PRIMARY KEY,
    report_id       TEXT NOT NULL,
    ticker          TEXT NOT NULL DEFAULT '',
    company         TEXT NOT NULL DEFAULT '',
    title           TEXT NOT NULL DEFAULT '',
    source          TEXT NOT NULL DEFAULT '',
    author_org      TEXT NOT NULL DEFAULT '',
    published_at    TEXT NOT NULL DEFAULT '',
    report_type     TEXT NOT NULL DEFAULT 'unknown',
    page_start      INTEGER NOT NULL DEFAULT 0,
    page_end        INTEGER NOT NULL DEFAULT 0,
    chunk_index     INTEGER NOT NULL DEFAULT 0,
    content         TEXT NOT NULL DEFAULT '',
    vector_id       TEXT,
    embedding_status TEXT NOT NULL DEFAULT 'pending'
        CHECK (embedding_status IN ('pending', 'success', 'failed')),
    created_at      TEXT NOT NULL,
    FOREIGN KEY(report_id) REFERENCES report_metadata(report_id)
);

CREATE INDEX IF NOT EXISTS idx_report_chunk_records_report_id
    ON report_chunk_records(report_id);
CREATE INDEX IF NOT EXISTS idx_report_chunk_records_ticker
    ON report_chunk_records(ticker);
CREATE INDEX IF NOT EXISTS idx_report_chunk_records_embedding_status
    ON report_chunk_records(embedding_status);

CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',

    risk_profile TEXT NOT NULL DEFAULT '' CHECK (
        risk_profile IN (
            '', 'conservative', 'moderate_conservative', 'moderate',
            'aggressive', 'very_aggressive'
        )
    ),
    investment_goal TEXT NOT NULL DEFAULT '' CHECK (
        investment_goal IN ('', 'short_term', 'mid_term', 'long_term')
    ),
    investment_amount_range TEXT NOT NULL DEFAULT '' CHECK (
        investment_amount_range IN (
            '', 'under_500', '500_2000', '2000_5000', 'over_5000'
        )
    ),
    investment_experience TEXT NOT NULL DEFAULT '' CHECK (
        investment_experience IN ('', 'beginner', 'intermediate', 'advanced')
    ),
    interest_sectors TEXT NOT NULL DEFAULT '[]',
    -- JSON 배열 문자열, 최대 3개. 예: '["반도체_종합전자", "2차전지_배터리"]'

    onboarding_done INTEGER NOT NULL DEFAULT 0,
    -- 0/1 (기존 report_files.is_valid_pdf와 동일한 boolean 표현 방식)

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawler_runs (
    run_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    total_found INTEGER NOT NULL DEFAULT 0,
    downloaded_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    failed_count INTEGER NOT NULL DEFAULT 0,
    price_rows_count INTEGER NOT NULL DEFAULT 0,
    macro_rows_count INTEGER NOT NULL DEFAULT 0,
    news_rows_count INTEGER NOT NULL DEFAULT 0,
    disclosure_rows_count INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS agent_jobs (
    job_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    job_type TEXT NOT NULL CHECK (job_type IN ('debate')),
    ticker TEXT NOT NULL DEFAULT '',
    company TEXT NOT NULL DEFAULT '',
    sector TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (
        status IN (
            'queued', 'running', 'debate_completed',
            'simulation_running', 'completed', 'failed'
        )
    ),
    request_json TEXT NOT NULL DEFAULT '{}',
    debate_result_json TEXT NOT NULL DEFAULT '{}',
    simulation_result_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agent_jobs_user_id ON agent_jobs(user_id);
CREATE INDEX IF NOT EXISTS idx_agent_jobs_status ON agent_jobs(status);
CREATE INDEX IF NOT EXISTS idx_agent_jobs_created_at ON agent_jobs(created_at);
