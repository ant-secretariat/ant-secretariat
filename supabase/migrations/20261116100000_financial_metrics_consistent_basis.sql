-- financial_metrics 계산 조건 보강 (PR #13 리뷰 반영)
-- 1) ROE: SQL sum()은 null을 건너뛰어, 한 분기 순이익이 비면 3개 분기 합으로 계산되던 것을 막는다
-- 2) 분기마다 연결(CFS)·별도(OFS)를 따로 고르므로, 비교·합산하는 분기끼리 기준이 같을 때만 계산한다
-- 값이 틀리게 보이는 것보다 비어 있는 편이 안전하다. 컬럼은 그대로다.
-- processing/functions/get_metric.py의 FINANCIAL_QUERY(시점 기준 조회)도 같은 조건을 쓴다.
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
    -- 전년 동기와 연결·별도 기준이 같을 때만 비교한다
    case when lag(seq, 4) over w = seq - 4 and lag(fs_div, 4) over w = fs_div
        then round(100.0 * revenue / nullif(lag(revenue, 4) over w, 0) - 100, 2)
    end as revenue_growth_yoy,
    -- 4개 분기 순이익이 모두 있고, 평균 자본에 쓰는 1년 전 분기까지 5개 분기가 같은 기준일 때만 계산한다
    case when lag(seq, 4) over w = seq - 4
          and count(net_income) over (w rows between 3 preceding and current row) = 4
          and min(fs_div) over (w rows between 4 preceding and current row)
            = max(fs_div) over (w rows between 4 preceding and current row)
        then round(
            100.0 * sum(net_income) over (w rows between 3 preceding and current row)
            / nullif((total_equity + lag(total_equity, 4) over w) / 2.0, 0), 2)
    end as roe_ttm
from chosen
window w as (partition by ticker order by seq);
