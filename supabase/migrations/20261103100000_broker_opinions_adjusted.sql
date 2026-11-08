-- 액면분할·병합 사건. 주식수가 크게 변했는데 시가총액은 거의 그대로면 분할로 본다.
-- 유상증자·합병은 시가총액이 함께 늘어 제외된다. 인적분할(주식수 감소폭이 작음)도 제외한다.
create view public.stock_split_events with (security_invoker = true) as
with changes as (
    select
        m.ticker,
        m.trade_date,
        m.shares_outstanding::double precision
            / nullif(lag(m.shares_outstanding) over w, 0) as share_ratio,
        p.market_cap::double precision
            / nullif(lag(p.market_cap) over w, 0) as cap_ratio
    from public.market_daily m
    join public.price_data p using (ticker, trade_date)
    window w as (partition by m.ticker order by m.trade_date)
)
select
    ticker,
    trade_date as effective_date,
    share_ratio,
    1 / share_ratio as price_factor      -- 분할 전 가격에 곱하면 분할 후 기준이 된다
from changes
where (share_ratio >= 1.5 or share_ratio <= 0.5)
  and cap_ratio between 0.8 and 1.25;

-- 목표가를 수정주가와 같은 기준으로 환산한다. 원본 target_price는 발표 당시 기준 그대로 둔다.
create view public.broker_opinions_adjusted with (security_invoker = true) as
select
    b.*,
    coalesce(f.price_factor, 1) as split_factor,
    round(b.target_price * coalesce(f.price_factor, 1))::bigint as target_price_adjusted
from public.broker_opinions b
left join lateral (
    select exp(sum(ln(e.price_factor))) as price_factor
    from public.stock_split_events e
    where e.ticker = b.ticker
      and e.effective_date > b.opinion_date
) f on true;
