-- 종목 30일 수익률의 시장·환율·금리 민감도
-- 시뮬레이션 what-if와 온톨로지 SENSITIVE_TO 엣지가 같이 쓴다.
create table public.sensitivities (
    ticker              text not null references public.companies (ticker),
    as_of               date not null,              -- 추정에 쓴 마지막 거래일
    factor              text not null check (factor in ('KOSPI', 'USD_KRW', 'KTB_3Y_KR')),
    method              text not null check (method in ('multi', 'simple')),  -- 세 요인 동시 회귀 / 단일 요인 회귀
    horizon_days        integer not null,
    beta                double precision,           -- 요인 1σ 변화당 종목 수익률(%)
    std_error           double precision,           -- Newey-West HAC
    ci_low              double precision,           -- 95% 신뢰구간
    ci_high             double precision,
    direction_uncertain boolean not null,           -- 신뢰구간이 0을 포함
    r_squared           double precision,
    factor_sigma        double precision,           -- 요인의 horizon 변화 1σ (KOSPI·환율 %, 금리 %p)
    corr_daily          double precision,           -- 일별 변화 상관계수 (온톨로지 엣지 가중치)
    n_obs               integer not null,
    window_start        date not null,
    fitted_at           timestamptz not null default now(),
    primary key (ticker, as_of, factor, method)
);

create index sensitivities_latest_idx on public.sensitivities (ticker, as_of desc);

alter table public.sensitivities enable row level security;
