-- 월별 상관을 "t월 주가 수익률 vs t+1월 요인 변화"로 바꾼다(지표는 월평균, 주가는 월말 종가라 같은 달끼리는 시점이 어긋남).
-- 같은 달 기준으로 계산했던 첫 결과(2026-11-10, 아직 아무도 쓰지 않음)는 지우고 다시 계산한다.
delete from public.monthly_correlations;

alter table public.monthly_correlations
    add column lead_months integer not null default 1;  -- 요인 변화가 주가 수익률보다 몇 달 뒤인지

comment on column public.monthly_correlations.as_of is '계산에 쓴 마지막 요인 달(1일)';
comment on column public.monthly_correlations.window_start is '계산에 쓴 첫 주가 달(1일)';

-- 뷰 끝에 lead_months를 덧붙인다 (create or replace view는 열을 끝에만 추가할 수 있다)
create or replace view public.sector_monthly_correlations with (security_invoker = true) as
with base as (
    select m.as_of, m.factor, m.ticker, m.corr_monthly, m.n_months, m.lead_months, c.sector_l1, c.sector_l2
    from public.monthly_correlations m
    join public.companies c using (ticker)
),
by_level as (
    select 'l1'::text as sector_level, sector_l1 as sector, as_of, factor, ticker, corr_monthly, n_months, lead_months
    from base where sector_l1 is not null
    union all
    select 'l2'::text, sector_l2, as_of, factor, ticker, corr_monthly, n_months, lead_months
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
    array_agg(b.ticker order by b.ticker) as tickers,
    max(b.lead_months) as lead_months
from by_level b
join latest l using (factor)
group by b.sector_level, b.sector, b.factor, b.as_of, l.as_of;
