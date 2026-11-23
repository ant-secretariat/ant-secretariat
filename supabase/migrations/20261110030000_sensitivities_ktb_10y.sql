-- 국고채 10년(KTB_10Y_KR)을 민감도 요인에 추가한다. 3년물과 일별 변화 상관이 0.9라 multi 회귀에는 넣지 않고
-- simple 회귀와 corr_daily만 낸다(method='simple' 행만 생김). 섹터 뷰 sector_sensitivities는 simple 행을 쓰므로 자동으로 포함된다.
alter table public.sensitivities drop constraint sensitivities_factor_check;
alter table public.sensitivities add constraint sensitivities_factor_check
    check (factor in ('KOSPI', 'USD_KRW', 'KTB_3Y_KR', 'KTB_10Y_KR'));
