-- 재무 시점 관리. 정정공시가 와도 덮어쓰지 않고 접수번호별로 쌓는다.
-- 과거 시점 기준 조회는 "그 날짜까지 접수된 것 중 가장 최근 접수번호"를 고른다.
alter table public.financials add column rcept_dt date;

-- DART 접수번호는 앞 8자리가 접수일(YYYYMMDD)이다
update public.financials set rcept_dt = to_date(left(rcept_no, 8), 'YYYYMMDD');

alter table public.financials alter column rcept_dt set not null;

alter table public.financials drop constraint financials_pkey;
alter table public.financials
    add primary key (ticker, fiscal_year, quarter, fs_div, account, rcept_no);

create index financials_ticker_rcept_dt_idx on public.financials (ticker, rcept_dt);

-- 항목마다 가장 최근 접수번호 1건 (현재 기준)
create view public.financials_latest with (security_invoker = true) as
select distinct on (ticker, fiscal_year, quarter, fs_div, account) *
from public.financials
order by ticker, fiscal_year, quarter, fs_div, account, rcept_no desc;

-- 항목마다 p_as_of까지 접수된 것 중 가장 최근 1건 (과거 시점 기준)
create function public.financials_as_of(p_as_of date)
returns setof public.financials
language sql
stable
as $$
    select distinct on (ticker, fiscal_year, quarter, fs_div, account) *
    from public.financials
    where rcept_dt <= p_as_of
    order by ticker, fiscal_year, quarter, fs_div, account, rcept_no desc
$$;

-- 지표 뷰는 현재 기준 최신 버전만 쓴다. 컬럼은 그대로다.
create or replace view public.financial_metrics with (security_invoker = true) as
with pivoted as (
    select
        ticker, fiscal_year, quarter, fs_div,
        max(period_end) as period_end,
        max(amount) filter (where account = 'revenue')           as revenue,
        max(amount) filter (where account = 'operating_income')  as operating_income,
        max(amount) filter (where account = 'net_income')        as net_income,
        max(amount) filter (where account = 'total_assets')      as total_assets,
        max(amount) filter (where account = 'total_liabilities') as total_liabilities,
        max(amount) filter (where account = 'total_equity')      as total_equity
    from public.financials_latest
    group by ticker, fiscal_year, quarter, fs_div
),
chosen as (
    select distinct on (ticker, fiscal_year, quarter) *, fiscal_year * 4 + quarter as seq
    from pivoted
    order by ticker, fiscal_year, quarter, (fs_div = 'CFS') desc
)
select
    ticker, fiscal_year, quarter, fs_div, period_end,
    revenue, operating_income, net_income, total_assets, total_liabilities, total_equity,
    round(100.0 * total_liabilities / nullif(total_equity, 0), 2) as debt_ratio,
    round(100.0 * operating_income / nullif(revenue, 0), 2)        as operating_margin,
    case when lag(seq, 4) over w = seq - 4
        then round(100.0 * revenue / nullif(lag(revenue, 4) over w, 0) - 100, 2)
    end as revenue_growth_yoy,
    case when lag(seq, 4) over w = seq - 4
        then round(
            100.0 * sum(net_income) over (w rows between 3 preceding and current row)
            / nullif((total_equity + lag(total_equity, 4) over w) / 2.0, 0), 2)
    end as roe_ttm
from chosen
window w as (partition by ticker order by seq);
