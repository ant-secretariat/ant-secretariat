-- 온톨로지 SENSITIVE_TO 입력값: 시장 효과를 뺀 민감도 (#56에서 형식 합의, #62 계산 코드)
--
-- 매달 python -m crawling.ontology_inputs monthly --save 가 기준일(as_of)별로 행을 쌓는다(덮어쓰지 않음).
-- 시드는 이 표를 읽어 종목 → 매크로·섹터 → 매크로 엣지의 weight와 판정 근거를 채운다(#64).
-- 한 표에 종목 행(level = 'ticker')과 섹터 행(level = 'l1' WICS 대분류, 'l2' 중분류)을 같이 둔다.
--   종목 행: n_obs, raw, adjusted, ci_low, ci_high, certain, p_value, q_value
--   섹터 행: n_tickers, raw_median, adjusted_median, same_sign, same_sign_ratio, n_certain, n_certain_pos, n_certain_neg, n_obs_min, n_obs_max
create table public.ontology_sensitivity_inputs (
    as_of            date not null,              -- 계산 기준일 (그날까지의 시세·지표만 씀)
    level            text not null check (level in ('ticker', 'l1', 'l2')),
    group_id         text not null,              -- 종목코드(ticker) 또는 섹터 이름(l1·l2)
    factor           text not null,              -- macro_data.indicator_id (KTB_3Y_KR, USD_KRW, BRENT, ...)
    frequency        text not null check (frequency in ('daily', 'monthly')),
    method           text not null,              -- 계산 방식과 시장 대용 (예: partial_corr_daily_kospi)
    window_start     date not null,              -- 실제로 쓴 첫 날(월별은 첫 달)
    window_end       date not null,              -- 실제로 쓴 마지막 날(월별은 마지막 달)

    -- 종목 행
    n_obs            integer,
    raw              double precision,           -- 원래 상관
    adjusted         double precision,           -- 양쪽에서 시장 효과를 뺀 상관(편상관)
    ci_low           double precision,           -- Fisher 95% 신뢰구간
    ci_high          double precision,
    certain          boolean,                    -- 신뢰구간이 0을 포함하지 않음
    p_value          double precision,
    q_value          double precision,           -- 같은 as_of·factor의 종목 행끼리 Benjamini-Hochberg 보정

    -- 섹터 행
    n_tickers        integer,
    raw_median       double precision,
    adjusted_median  double precision,
    same_sign        integer,                    -- adjusted_median과 부호가 같은 종목 수
    same_sign_ratio  double precision,
    n_certain        integer,                    -- 방향 확실 종목 수
    n_certain_pos    integer,
    n_certain_neg    integer,
    n_obs_min        integer,
    n_obs_max        integer,

    computed_at      timestamptz not null default now(),
    primary key (as_of, level, group_id, factor),
    check (window_start <= window_end),
    check (
        (level = 'ticker' and n_obs is not null and adjusted is not null and certain is not null and n_tickers is null)
        or (level <> 'ticker' and n_tickers is not null and adjusted_median is not null and n_obs is null)
    )
);

create index ontology_sensitivity_inputs_lookup_idx
    on public.ontology_sensitivity_inputs (level, group_id, factor, as_of desc);

alter table public.ontology_sensitivity_inputs enable row level security;
