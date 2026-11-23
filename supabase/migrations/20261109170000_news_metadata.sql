-- 뉴스 기사 목록과 청킹 상태 (네이버 API HUB 뉴스 검색 + 원문 페이지 본문). 본문은 document_chunks(document_type='news')에 둔다.
-- 같은 기사가 여러 종목 검색에 걸리면 한 행으로 두고 mentioned_tickers에 종목을 모은다.
create table public.news_metadata (
    news_id            text primary key,              -- NEWS_{원문 URL SHA-1 앞 16자}
    ticker             text not null,                 -- 처음 수집한 종목
    company            text not null default '',
    mentioned_tickers  text[] not null default '{}',  -- 이 기사가 다루는 T1 종목
    title              text not null default '',
    summary            text not null default '',      -- 검색 API 요약문
    press              text not null default '',      -- 언론사 도메인 (Evidence.author_org)
    published_at       timestamptz not null,
    original_url       text not null,
    source             text not null default 'NAVER_NEWS',
    chunk_status       text not null default 'pending'
                       check (chunk_status in ('pending', 'chunked', 'failed', 'no_text')),
    chunk_count        integer,
    chunker_version    text,
    error_message      text,
    chunked_at         timestamptz,
    collected_at       timestamptz not null default now()
);

create index news_metadata_ticker_published_idx on public.news_metadata (ticker, published_at desc);
create index news_metadata_mentioned_idx on public.news_metadata using gin (mentioned_tickers);
create index news_metadata_status_idx on public.news_metadata (chunk_status);

alter table public.news_metadata enable row level security;
