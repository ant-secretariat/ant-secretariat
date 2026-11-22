-- DART 주요 재무계정 (OpenDART fnlttMultiAcnt)
-- 손익 항목은 분기 단독(3개월) 값과 연초부터 누적 값을 함께 둔다. 4분기 단독은 연간 − 3분기 누적.
create table public.financials (
    ticker       text not null references public.companies (ticker),
    fiscal_year  integer not null,
    quarter      smallint not null check (quarter between 1 and 4),
    fs_div       text not null check (fs_div in ('CFS', 'OFS')),  -- 연결 / 별도
    account      text not null,         -- 표준 계정 키 (revenue, operating_income, total_equity 등)
    account_nm   text not null,         -- DART 원래 계정명
    period_end   date not null,
    amount       bigint,                -- 재무상태표: 기말 잔액, 손익: 해당 분기 3개월
    amount_ytd   bigint,                -- 손익: 연초부터 누적, 재무상태표: null
    rcept_no     text not null,         -- 접수번호 (정정 공시 추적)
    updated_at   timestamptz not null default now(),
    primary key (ticker, fiscal_year, quarter, fs_div, account)
);

alter table public.financials enable row level security;

-- 분기별 파생 지표. 연결재무제표가 있으면 연결, 없으면 별도 기준.
-- ROE는 최근 4개 분기 순이익 합 / (현재·1년 전 자본총계 평균). 순이익은 지배주주 귀속분이 아닌 전체 당기순이익.
create view public.financial_metrics with (security_invoker = true) as
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
    from public.financials
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
