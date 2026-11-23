-- 월별 지표(CPI, 유가, D램 수출물가)와 종목 월 수익률의 상관.
-- 일별 시세는 3년 치만 두므로, 10년 치 월말 종가만 따로 저장해 월별 상관을 계산한다(용량을 아끼려고 일별은 저장하지 않음).

-- 월말 수정종가 (pykrx 월봉). month는 해당 월 1일. 끝나지 않은 이번 달은 넣지 않는다
create table public.price_monthly (
    ticker      text not null references public.companies (ticker),
    month       date not null check (extract(day from month) = 1),
    close       double precision not null,
    volume      bigint,
    created_at  timestamptz not null default now(),
    primary key (ticker, month)
);

-- 종목별 월별 상관. 종목 월 로그수익률과 요인 월 로그변화의 피어슨 상관(최근 최대 120개월)
create table public.monthly_correlations (
    ticker       text not null references public.companies (ticker),
    as_of        date not null,              -- 계산에 쓴 마지막 달(1일)
    factor       text not null,              -- macro_data.indicator_id (CPI_KR, BRENT, DRAM_EXPORT_PRICE 등)
    corr_monthly double precision not null,
    n_months     integer not null,           -- 계산에 쓴 개월 수 (최근 상장 종목은 짧다)
    ci_low       double precision,           -- 95% 신뢰구간 (Fisher z)
    ci_high      double precision,
    window_start date not null,              -- 계산에 쓴 첫 달
    fitted_at    timestamptz not null default now(),
    primary key (ticker, as_of, factor)
);

create index monthly_correlations_factor_idx on public.monthly_correlations (factor, as_of desc);

alter table public.price_monthly enable row level security;
alter table public.monthly_correlations enable row level security;

-- 섹터(WICS l1/l2)별 월별 상관. sector_sensitivities와 같은 모양이고, 요인마다 가장 최근 as_of를 is_latest로 표시한다
create view public.sector_monthly_correlations with (security_invoker = true) as
with base as (
    select m.as_of, m.factor, m.ticker, m.corr_monthly, m.n_months, c.sector_l1, c.sector_l2
    from public.monthly_correlations m
    join public.companies c using (ticker)
),
by_level as (
    select 'l1'::text as sector_level, sector_l1 as sector, as_of, factor, ticker, corr_monthly, n_months
    from base where sector_l1 is not null
    union all
    select 'l2'::text, sector_l2, as_of, factor, ticker, corr_monthly, n_months
    from base where sector_l2 is not null
),
latest as (
    select factor, max(as_of) as as_of from public.monthly_correlations group by factor
)
select
    b.sector_level,
    b.sector,
    b.factor,
    b.as_of,
    b.as_of = l.as_of as is_latest,
    count(*)::integer as n_tickers,
    percentile_cont(0.5) within group (order by b.corr_monthly) as corr_monthly_median,
    percentile_cont(0.25) within group (order by b.corr_monthly) as corr_monthly_p25,
    percentile_cont(0.75) within group (order by b.corr_monthly) as corr_monthly_p75,
    min(b.n_months) as n_months_min,
    percentile_cont(0.5) within group (order by b.n_months) as n_months_median,
    array_agg(b.ticker order by b.ticker) as tickers
from by_level b
join latest l using (factor)
group by b.sector_level, b.sector, b.factor, b.as_of, l.as_of;

comment on view public.sector_monthly_correlations is
    '섹터(WICS l1/l2)별 월별 상관 중앙값·사분위·종목 수·개월 수. 종목 수나 개월 수가 작으면 불안정';
