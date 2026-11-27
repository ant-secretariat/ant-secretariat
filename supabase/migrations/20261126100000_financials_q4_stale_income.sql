-- 4분기 손익 행에 미래 정보가 섞인 경우를 바로잡는다 (#16 리뷰 1번, #55).
--
-- 4분기 단독 손익은 "연간 − 3분기 누적"이다. 3분기 정정공시가 사업보고서보다 늦게 나왔는데 적재는 정정 뒤에 했으면,
-- 4분기 행은 사업보고서 접수번호(이른 날짜)를 달고 있지만 값은 정정된 3분기(늦은 날짜)로 계산돼 있다.
-- 그러면 financials_as_of(그 사이 날짜)가 그때는 아직 없던 값을 돌려준다.
-- 운영 DB 해당(2026-11-26 확인): KB금융 105560 2023년 4분기 CFS·OFS × 영업이익·세전이익·순이익 6행.
-- 원래 3분기 보고서는 적재돼 있지 않아 그 시점의 4분기 단독값은 다시 만들 수 없다.
--
-- 처리:
-- 1. 정정된 3분기 접수번호로 같은 값의 새 행을 넣는다(4분기 단독값을 알 수 있게 된 날짜).
-- 2. 기존 행(사업보고서 접수번호)은 단독값(amount)만 비운다. 누적값(amount_ytd = 연간)은 사업보고서로 그때 이미 알 수 있었으므로 둔다.
-- 적재기는 이미 "더 늦게 접수된 쪽의 접수번호"를 쓰므로(financial_rows), 다시 적재해도 1번 행과 같은 행이 나온다.

create temporary table stale_q4 on commit drop as
select f4.ticker, f4.fiscal_year, f4.fs_div, f4.account, f4.rcept_no as old_rcept_no, max(q3.rcept_no) as q3_rcept_no
from public.financials f4
join public.financials q3
  on q3.quarter = 3
 and (q3.ticker, q3.fiscal_year, q3.fs_div, q3.account) = (f4.ticker, f4.fiscal_year, f4.fs_div, f4.account)
where f4.quarter = 4
  and f4.amount is not null and f4.amount_ytd is not null and q3.amount_ytd is not null
  and q3.rcept_no > f4.rcept_no
  and f4.amount = f4.amount_ytd - q3.amount_ytd
  -- 그 시점에 이미 있던 3분기 버전으로도 같은 값이 나오면 미래 정보가 아니다
  and not exists (
      select 1 from public.financials q3_known
      where q3_known.quarter = 3
        and (q3_known.ticker, q3_known.fiscal_year, q3_known.fs_div, q3_known.account)
          = (f4.ticker, f4.fiscal_year, f4.fs_div, f4.account)
        and q3_known.rcept_no <= f4.rcept_no
        and f4.amount = f4.amount_ytd - q3_known.amount_ytd
  )
group by f4.ticker, f4.fiscal_year, f4.fs_div, f4.account, f4.rcept_no;

insert into public.financials
    (ticker, fiscal_year, quarter, fs_div, account, account_nm, period_end, amount, amount_ytd, rcept_no, rcept_dt, updated_at)
select f4.ticker, f4.fiscal_year, 4, f4.fs_div, f4.account, f4.account_nm, f4.period_end, f4.amount, f4.amount_ytd,
       s.q3_rcept_no, to_date(left(s.q3_rcept_no, 8), 'YYYYMMDD'), now()
from stale_q4 s
join public.financials f4
  on f4.quarter = 4
 and (f4.ticker, f4.fiscal_year, f4.fs_div, f4.account, f4.rcept_no)
   = (s.ticker, s.fiscal_year, s.fs_div, s.account, s.old_rcept_no)
on conflict (ticker, fiscal_year, quarter, fs_div, account, rcept_no) do nothing;

update public.financials f4
set amount = null, updated_at = now()
from stale_q4 s
where f4.quarter = 4
  and (f4.ticker, f4.fiscal_year, f4.fs_div, f4.account, f4.rcept_no)
    = (s.ticker, s.fiscal_year, s.fs_div, s.account, s.old_rcept_no);
