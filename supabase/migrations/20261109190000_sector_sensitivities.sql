-- 섹터별 민감도: 소속 종목 corr_daily를 WICS 대분류(l1)·중분류(l2)별로 묶은 값
-- 온톨로지 섹터→매크로 SENSITIVE_TO 엣지 가중치용. KRX 업종지수는 WICS와 분류가 달라 종목 값을 묶는다.
-- corr_daily는 요인 하나와의 일별 상관이라 multi/simple 행에 같은 값이 있어 simple 행만 쓴다.
-- 종목이 1~2개뿐인 섹터는 값이 불안정하니 n_tickers를 보고 거른다.
-- 기본은 is_latest = true 행만 쓰면 되고, 과거 as_of 행은 시점 재현용으로 남긴다.
create view public.sector_sensitivities with (security_invoker = true) as
with base as (
    select s.as_of, s.factor, s.ticker, s.corr_daily, c.sector_l1, c.sector_l2
    from public.sensitivities s
    join public.companies c using (ticker)
    where s.method = 'simple' and s.corr_daily is not null
),
by_level as (
    select 'l1'::text as sector_level, sector_l1 as sector, as_of, factor, ticker, corr_daily
    from base where sector_l1 is not null
    union all
    select 'l2'::text, sector_l2, as_of, factor, ticker, corr_daily
    from base where sector_l2 is not null
)
select
    sector_level,
    sector,
    factor,
    as_of,
    as_of = (select max(as_of) from public.sensitivities) as is_latest,
    count(*)::integer as n_tickers,
    percentile_cont(0.5) within group (order by corr_daily) as corr_daily_median,
    percentile_cont(0.25) within group (order by corr_daily) as corr_daily_p25,
    percentile_cont(0.75) within group (order by corr_daily) as corr_daily_p75,
    array_agg(ticker order by ticker) as tickers
from by_level
group by sector_level, sector, factor, as_of;

comment on view public.sector_sensitivities is
    '섹터(WICS l1/l2)별 corr_daily 중앙값·사분위·종목 수. 소속 종목 값을 묶은 것이며 n_tickers가 작으면 불안정';
