-- 종목별 일별 투자자 순매수와 공매도 (pykrx)
-- 공매도 잔고는 KRX가 약 2거래일 늦게 공개해서, 최근 며칠은 잔고가 비어 있다가 다음 갱신 때 채워진다.
create table public.investor_flow_daily (
    ticker                  text not null references public.companies (ticker),
    trade_date              date not null,
    inst_net_value          bigint,             -- 기관합계 순매수 금액(원)
    foreign_net_value       bigint,             -- 외국인합계 순매수 금액(원)
    individual_net_value    bigint,             -- 개인 순매수 금액(원)
    other_corp_net_value    bigint,             -- 기타법인 순매수 금액(원)
    inst_net_volume         bigint,             -- 기관합계 순매수 수량(주)
    foreign_net_volume      bigint,             -- 외국인합계 순매수 수량(주)
    individual_net_volume   bigint,             -- 개인 순매수 수량(주)
    other_corp_net_volume   bigint,             -- 기타법인 순매수 수량(주)
    short_volume            bigint,             -- 공매도 거래량(주)
    short_value             bigint,             -- 공매도 거래대금(원)
    short_volume_ratio      double precision,   -- 공매도 거래량 비중(%)
    short_balance           bigint,             -- 공매도 잔고 수량(주)
    short_balance_value     bigint,             -- 공매도 잔고 금액(원)
    short_balance_ratio     double precision,   -- 공매도 잔고 비중(상장주식수 대비 %)
    updated_at              timestamptz not null default now(),
    primary key (ticker, trade_date)
);

alter table public.investor_flow_daily enable row level security;
