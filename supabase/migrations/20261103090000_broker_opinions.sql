-- 증권사 목표주가·투자의견 (KIS 종목투자의견 API)
-- opinion은 증권사가 쓴 값 그대로(BUY, 매수, Outperform 등), opinion_norm은 buy/hold/sell로 통일한 값.
create table public.broker_opinions (
    ticker        text not null references public.companies (ticker),
    opinion_date  date not null,
    broker        text not null,
    opinion       text,
    opinion_norm  text check (opinion_norm in ('buy', 'hold', 'sell')),  -- 분류할 수 없는 값은 null
    prev_opinion  text,
    target_price  bigint,                -- 원. 목표가가 없으면 null
    updated_at    timestamptz not null default now(),
    primary key (ticker, opinion_date, broker)
);

alter table public.broker_opinions enable row level security;
