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
