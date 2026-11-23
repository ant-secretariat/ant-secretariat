-- 목표주가·투자의견의 유효기간. 같은 증권사가 같은 종목에 다음 의견을 내면 이전 의견은 그날로 끝난다.
-- valid_from은 발표일, superseded_at은 같은 증권사의 다음 발표일(아직 없으면 null).
create or replace view public.broker_opinions_adjusted with (security_invoker = true) as
select
    b.*,
    coalesce(f.price_factor, 1) as split_factor,
    round(b.target_price * coalesce(f.price_factor, 1))::bigint as target_price_adjusted,
    b.opinion_date as valid_from,
    lead(b.opinion_date) over (partition by b.ticker, b.broker order by b.opinion_date) as superseded_at
from public.broker_opinions b
left join lateral (
    select exp(sum(ln(e.price_factor))) as price_factor
    from public.stock_split_events e
    where e.ticker = b.ticker
      and e.effective_date > b.opinion_date
) f on true;
