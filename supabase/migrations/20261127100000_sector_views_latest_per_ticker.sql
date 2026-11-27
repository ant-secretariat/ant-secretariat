-- 섹터 뷰의 "최신"(is_latest)을 종목마다 가장 최근 값으로 묶는다 (#34 리뷰, #41).
--
-- 이전: sector_sensitivities는 표 전체의 가장 늦은 as_of 하나만 최신으로 봤다(sector_monthly_correlations는 요인별).
--       그래서 일부 종목만 다시 계산하면(sim_loader --tickers 등) 최신 행이 그 종목들로 줄어들었다.
-- 이번: 종목·요인마다 가장 최근 값을 모아 섹터 최신을 만든다. as_of는 그중 가장 늦은 날이다.
--       다만 가장 늦은 날보다 40일 넘게 오래된 종목 값은 넣지 않는다(대상에서 빠진 종목 값이 계속 남지 않게).
--       매달 다시 계산하므로 40일이면 한 번 빠진 재계산까지만 덮는다.
-- 과거 시점 행(is_latest = false)은 as_of마다 그대로 둔다. 최신 행과 날짜가 같으면 최신 행 하나만 남긴다.
-- 열 이름·순서·타입은 그대로다(create or replace view).
-- 지금 데이터(모든 종목이 같은 날 계산됨)에서는 결과가 이전과 같다.

create or replace view public.sector_sensitivities with (security_invoker = true) as
with base as (
    select s.as_of, s.factor, s.ticker, s.corr_daily, c.sector_l1, c.sector_l2,
           s.as_of = max(s.as_of) over (partition by s.ticker, s.factor) as ticker_latest
    from public.sensitivities s
    join public.companies c using (ticker)
    where s.method = 'simple' and s.corr_daily is not null
),
by_level as (
    select 'l1'::text as sector_level, sector_l1 as sector, as_of, factor, ticker, corr_daily, ticker_latest
    from base where sector_l1 is not null
    union all
    select 'l2'::text, sector_l2, as_of, factor, ticker, corr_daily, ticker_latest
    from base where sector_l2 is not null
),
newest as (
    select max(as_of) as as_of from public.sensitivities
),
latest as (
    select
        b.sector_level, b.sector, b.factor, max(b.as_of) as as_of, true as is_latest,
        count(*)::integer as n_tickers,
        percentile_cont(0.5) within group (order by b.corr_daily) as corr_daily_median,
        percentile_cont(0.25) within group (order by b.corr_daily) as corr_daily_p25,
        percentile_cont(0.75) within group (order by b.corr_daily) as corr_daily_p75,
        array_agg(b.ticker order by b.ticker) as tickers
    from by_level b, newest n
    where b.ticker_latest and b.as_of > n.as_of - 40
    group by b.sector_level, b.sector, b.factor
),
history as (
    select
        sector_level, sector, factor, as_of, false as is_latest,
        count(*)::integer as n_tickers,
        percentile_cont(0.5) within group (order by corr_daily) as corr_daily_median,
        percentile_cont(0.25) within group (order by corr_daily) as corr_daily_p25,
        percentile_cont(0.75) within group (order by corr_daily) as corr_daily_p75,
        array_agg(ticker order by ticker) as tickers
    from by_level
    group by sector_level, sector, factor, as_of
)
select * from latest
union all
select h.* from history h
where not exists (
    select 1 from latest l
    where (l.sector_level, l.sector, l.factor, l.as_of) = (h.sector_level, h.sector, h.factor, h.as_of)
);

comment on view public.sector_sensitivities is
    '섹터(WICS l1/l2)별 corr_daily 중앙값·사분위·종목 수. is_latest 행은 종목마다 가장 최근 값(가장 늦은 날부터 40일 안)을 묶은 것, 나머지는 as_of별 스냅샷. n_tickers가 작으면 불안정';

create or replace view public.sector_monthly_correlations with (security_invoker = true) as
with base as (
    select m.as_of, m.factor, m.ticker, m.corr_monthly, m.n_months, m.lead_months, c.sector_l1, c.sector_l2,
           m.as_of = max(m.as_of) over (partition by m.ticker, m.factor) as ticker_latest
    from public.monthly_correlations m
    join public.companies c using (ticker)
),
by_level as (
    select 'l1'::text as sector_level, sector_l1 as sector, as_of, factor, ticker, corr_monthly, n_months, lead_months,
           ticker_latest
    from base where sector_l1 is not null
    union all
    select 'l2'::text, sector_l2, as_of, factor, ticker, corr_monthly, n_months, lead_months, ticker_latest
    from base where sector_l2 is not null
),
newest as (
    -- 요인마다 발표 시차가 달라(1~2달) 가장 늦은 달을 요인별로 본다
    select factor, max(as_of) as as_of from public.monthly_correlations group by factor
),
latest as (
    select
        b.sector_level, b.sector, b.factor, max(b.as_of) as as_of, true as is_latest,
        count(*)::integer as n_tickers,
        percentile_cont(0.5) within group (order by b.corr_monthly) as corr_monthly_median,
        percentile_cont(0.25) within group (order by b.corr_monthly) as corr_monthly_p25,
        percentile_cont(0.75) within group (order by b.corr_monthly) as corr_monthly_p75,
        min(b.n_months) as n_months_min,
        percentile_cont(0.5) within group (order by b.n_months) as n_months_median,
        array_agg(b.ticker order by b.ticker) as tickers,
        max(b.lead_months) as lead_months
    from by_level b
    join newest n using (factor)
    where b.ticker_latest and b.as_of > n.as_of - 40
    group by b.sector_level, b.sector, b.factor
),
history as (
    select
        sector_level, sector, factor, as_of, false as is_latest,
        count(*)::integer as n_tickers,
        percentile_cont(0.5) within group (order by corr_monthly) as corr_monthly_median,
        percentile_cont(0.25) within group (order by corr_monthly) as corr_monthly_p25,
        percentile_cont(0.75) within group (order by corr_monthly) as corr_monthly_p75,
        min(n_months) as n_months_min,
        percentile_cont(0.5) within group (order by n_months) as n_months_median,
        array_agg(ticker order by ticker) as tickers,
        max(lead_months) as lead_months
    from by_level
    group by sector_level, sector, factor, as_of
)
select * from latest
union all
select h.* from history h
where not exists (
    select 1 from latest l
    where (l.sector_level, l.sector, l.factor, l.as_of) = (h.sector_level, h.sector, h.factor, h.as_of)
);
