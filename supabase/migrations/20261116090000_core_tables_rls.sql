-- 핵심 테이블 RLS와 공개 역할 쓰기 권한 회수, sim_params 실패 상태 추가 (PR #11 리뷰 반영)
--
-- 적재기와 에이전트는 SUPABASE_DB_URL로 테이블 소유자 역할(postgres)로 붙으므로 RLS의 영향을 받지 않는다.
-- 공개 키(anon)·로그인 사용자(authenticated)는 Data API로 읽거나 쓸 수 없게 한다.
-- 앱이 나중에 API로 직접 읽어야 하면 그때 테이블별 읽기 정책만 추가한다.

alter table public.companies    enable row level security;
alter table public.price_data   enable row level security;
alter table public.market_daily enable row level security;
alter table public.index_daily  enable row level security;
alter table public.macro_data   enable row level security;
alter table public.sim_params   enable row level security;

-- TRUNCATE는 RLS를 거치지 않으므로 함께 회수한다. 이 마이그레이션 시점의 public 테이블 전부가 대상이다
revoke insert, update, delete, truncate on all tables in schema public from anon, authenticated;
-- 앞으로 만드는 테이블에도 같은 기본값을 적용한다
alter default privileges in schema public revoke insert, update, delete, truncate on tables from anon, authenticated;

-- GARCH 적합 중 예외가 난 종목을 '결과 없음'과 구분해 남긴다
alter table public.sim_params drop constraint sim_params_status_check;
alter table public.sim_params add constraint sim_params_status_check
    check (status in ('ok', 'not_converged', 'insufficient_history', 'error'));
