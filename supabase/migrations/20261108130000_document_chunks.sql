-- 문서 청크 (RAG 검색용). 임베딩은 나중에 채우고, 그 전에는 키워드 검색(BM25)으로 찾는다.
create extension if not exists vector with schema extensions;

-- 증권사 리포트 목록과 청킹 상태. PDF 원본은 저장하지 않는다 (청킹 후 삭제)
create table public.report_metadata (
    report_id       text primary key,           -- NAVER_{종목코드}_{발행일}_{해시}
    ticker          text not null,
    company         text not null default '',
    title           text not null default '',
    source          text not null,              -- 수집처 (NAVER, KIRS)
    broker          text not null default '',   -- 증권사
    published_at    date not null,
    original_url    text,
    pdf_url         text,
    pdf_sha256      text,
    chunk_status    text not null default 'pending'
                    check (chunk_status in ('pending', 'chunked', 'failed', 'no_pdf')),
    chunk_count     integer,
    chunker_version text,                       -- 청커를 고치면 이 값이 다른 리포트만 다시 자른다
    error_message   text,
    chunked_at      timestamptz,
    collected_at    timestamptz not null default now()
);

create index report_metadata_ticker_published_idx on public.report_metadata (ticker, published_at desc);
create index report_metadata_status_idx on public.report_metadata (chunk_status);

-- 검색 단위 청크. 리포트 외에 뉴스·공시도 같은 표에 document_type으로 구분해 넣는다
-- 임베딩 입력은 머리말 [회사(종목코드) | 증권사 | 날짜 | 소제목] + body로, 저장하지 않고 그때 만든다
create table public.document_chunks (
    chunk_id          text primary key,         -- {doc_id}:{본문 SHA-1 앞 12자}
    doc_id            text not null,            -- 리포트면 report_metadata.report_id
    document_type     text not null check (document_type in ('report', 'news', 'disclosure', 'macro')),
    ticker            text,
    company           text,
    broker            text,                     -- 계약서 Evidence.author_org
    published_at      date not null,
    title             text not null default '', -- 문서 제목
    url               text,                     -- 원문 주소
    chunk_index       integer not null,
    chunk_type        text not null check (chunk_type in ('text', 'table')),
    section_title     text not null default '',
    section_type      text not null default 'body' check (section_type in ('body', 'disclaimer')),
    page_start        integer,
    page_end          integer,
    body              text not null,
    table_structure   text check (table_structure in ('intact', 'text_only')),
    extraction_method text not null default 'pymupdf',
    mentioned_tickers text[] not null default '{}',  -- 본문이 다루는 종목 (온톨로지 연결용)
    issue_ids         text[] not null default '{}',  -- 온톨로지 ISSUE 노드 ID
    embedding         extensions.vector(1024),       -- solar-embedding-2 (passage). 채우기 전에는 null
    embedding_model   text,
    created_at        timestamptz not null default now()
);

create index document_chunks_doc_idx on public.document_chunks (doc_id);
create index document_chunks_ticker_published_idx on public.document_chunks (ticker, published_at desc);
create index document_chunks_mentioned_idx on public.document_chunks using gin (mentioned_tickers);
create index document_chunks_issue_idx on public.document_chunks using gin (issue_ids);

alter table public.report_metadata enable row level security;
alter table public.document_chunks enable row level security;
