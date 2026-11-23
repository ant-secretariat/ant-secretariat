-- DART 공시 목록과 청킹 상태. 본문은 document_chunks(document_type='disclosure')에 둔다.
-- 토론 근거로 쓸 수시공시·주요사항보고서만 넣는다(실적 잠정, 공급계약, 증자·자사주·배당, 출자·투자, 해명·소송 등).
-- 정기보고서·지분공시·증권 발행 서류는 다른 테이블(financials, insider_holdings)이 다루거나 근거 가치가 낮아 뺀다.
create table public.disclosure_metadata (
    rcept_no           text primary key,              -- DART 접수번호 (document_chunks.doc_id = 'DART_' || rcept_no)
    ticker             text not null references public.companies (ticker),
    corp_code          text not null,
    company            text not null default '',
    report_name        text not null,                 -- DART 보고서명 그대로 ([기재정정] 등 포함)
    category           text not null,                 -- earnings / contract / capital / shareholder_return / investment / risk / other
    is_correction      boolean not null default false,-- [기재정정]·[첨부정정] 등 정정 공시
    filer              text not null default '',      -- 제출인 (Evidence.author_org)
    remark             text not null default '',      -- DART 비고 (유: 유가증권, 코: 코스닥, 정: 정정 등)
    disclosed_at       date not null,                 -- 접수일 (as_of 기준)
    original_url       text not null,
    source             text not null default 'DART',
    chunk_status       text not null default 'pending'
                       check (chunk_status in ('pending', 'chunked', 'failed', 'no_text')),
    chunk_count        integer,
    chunker_version    text,
    error_message      text,
    chunked_at         timestamptz,
    collected_at       timestamptz not null default now()
);

create index disclosure_metadata_ticker_date_idx on public.disclosure_metadata (ticker, disclosed_at desc);
create index disclosure_metadata_status_idx on public.disclosure_metadata (chunk_status);

alter table public.disclosure_metadata enable row level security;
