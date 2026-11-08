-- 대주주·임원 지분 변동 (DART 지분공시 종합정보)
-- report_kind: major = 대량보유 상황보고(5% 이상), insider = 임원·주요주주 소유보고
-- 접수일(rcept_dt) 기준으로 시점 조회한다. DART는 최근 약 2년 치를 주고, 매번 전체를 받아 덮어쓴다.
create table public.insider_holdings (
    report_kind     text not null check (report_kind in ('major', 'insider')),
    rcept_no        text not null,              -- 접수번호
    reporter        text not null,              -- 보고자
    ticker          text not null references public.companies (ticker),
    rcept_dt        date not null,              -- 접수일
    position        text,                       -- insider: 직위 (대표사장, 독립이사 등)
    exec_registered text,                       -- insider: 등기임원 / 비등기임원
    major_holder    text,                       -- insider: 주요주주 여부
    report_type     text,                       -- major: 보고 구분 (일반, 약식 등)
    report_reason   text,                       -- major: 보고 사유
    shares          bigint,                     -- 보유(소유) 주식수
    shares_change   bigint,                     -- 주식수 증감
    ratio           double precision,           -- 보유(소유) 비율(%)
    ratio_change    double precision,           -- 비율 증감(%p)
    contract_shares bigint,                     -- major: 주요 계약 체결 주식수
    contract_ratio  double precision,           -- major: 주요 계약 체결 비율(%)
    updated_at      timestamptz not null default now(),
    primary key (report_kind, rcept_no, reporter)
);

create index insider_holdings_ticker_rcept_dt_idx on public.insider_holdings (ticker, rcept_dt);

alter table public.insider_holdings enable row level security;
