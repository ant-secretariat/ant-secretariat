-- 데이터 에이전트 핵심 정형 테이블
-- 종목 마스터, 시세, 펀더멘털, 지수, 매크로, 시뮬레이션 파라미터

-- 종목 마스터. 상장폐지 종목도 과거 시세 참조를 위해 남겨둔다.
create table public.companies (
    ticker          text primary key check (ticker ~ '^[0-9A-Z]{6}$'),
    name            text not null,
    aliases         text[] not null default '{}',
    market          text not null check (market in ('KOSPI', 'KOSDAQ', 'KONEX')),
    corp_code       text,                       -- DART 고유번호(8자리)
    sector_l1       text,                       -- WICS 대분류
    sector_l2       text,                       -- WICS 중분류
    is_preferred    boolean not null default false,
    listed          boolean not null default true,
    delisted_at     date,
    tier            text not null default 'T0' check (tier in ('T0', 'T1', 'T2')),
    is_core         boolean not null default false,  -- 초기 시총 상위 100개, 강등 제외
    last_queried_at timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);

create index companies_tier_idx on public.companies (tier);
create index companies_corp_code_idx on public.companies (corp_code);

-- 일별 시세 (pykrx 수정주가)
create table public.price_data (
    ticker        text not null references public.companies (ticker),
    trade_date    date not null,
    open          double precision,
    high          double precision,
    low           double precision,
    close         double precision,
    volume        bigint,
    trading_value bigint,
    market_cap    bigint,
    created_at    timestamptz not null default now(),
    primary key (ticker, trade_date)
);

-- 같은 날 전종목 조회(변동성 기준선, 시총 순위)용
create index price_data_trade_date_idx on public.price_data (trade_date);

-- 일별 펀더멘털·주식수 (pykrx)
create table public.market_daily (
    ticker             text not null references public.companies (ticker),
    trade_date         date not null,
    per                double precision,
    pbr                double precision,
    eps                double precision,
    bps                double precision,
    dividend_yield     double precision,
    dps                double precision,
    shares_outstanding bigint,
    foreign_ratio      double precision,   -- 외국인 보유 비율(%)
    created_at         timestamptz not null default now(),
    primary key (ticker, trade_date)
);

create index market_daily_trade_date_idx on public.market_daily (trade_date);

-- 일별 지수 (pykrx). 1001 코스피, 2001 코스닥, 1028 코스피200
create table public.index_daily (
    index_code    text not null,
    index_name    text not null default '',
    trade_date    date not null,
    open          double precision,
    high          double precision,
    low           double precision,
    close         double precision,
    volume        bigint,
    trading_value bigint,
    created_at    timestamptz not null default now(),
    primary key (index_code, trade_date)
);

-- 매크로 지표 전체 이력 (ECOS). 월간 지표의 date는 해당 월 1일.
create table public.macro_data (
    indicator_id   text not null,
    indicator_name text not null default '',
    date           date not null,
    value          double precision,
    unit           text not null default '',
    frequency      text not null check (frequency in ('daily', 'monthly', 'quarterly')),
    country        text not null default 'KR',
    source         text not null,
    created_at     timestamptz not null default now(),
    primary key (indicator_id, date)
);

-- 시뮬레이션 파라미터. 모델 구조는 params_json에만 두고 컬럼에 고정하지 않는다.
create table public.sim_params (
    ticker       text not null references public.companies (ticker),
    as_of        date not null,              -- 적합에 쓴 마지막 거래일
    model_id     text not null,              -- 예: gjr_garch_fhs_v1
    status       text not null check (status in ('ok', 'not_converged', 'insufficient_history')),
    n_obs        integer,
    params_json  jsonb not null default '{}',
    fitted_at    timestamptz not null default now(),
    primary key (ticker, as_of, model_id)
);

create index sim_params_latest_idx on public.sim_params (ticker, model_id, as_of desc);
