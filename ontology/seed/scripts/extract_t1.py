"""T1(core) 종목 CSV 검증 — 수경 파이프라인 companies.is_core 내보내기

v0.2까지는 외부 시총 데이터셋(marcap)으로 KOSPI 상위 100을 직접 뽑았지만, v0.3부터 T1은
수경 파이프라인이 정한 100종목을 그대로 쓴다 (2026-10-22 시총 순위로 지정, 이후 고정).
이 스크립트는 그 CSV를 만들지 않고, build_seed.py에 넣기 전에 형식만 검증한다.

내보내기 (Supabase SQL):
    select ticker, name, market, sector_l1, sector_l2
    from companies where is_core order by market, ticker;

사용법: python extract_t1.py <core_companies.csv>
검사: 100행 · ticker 형식 ^[0-9A-Z]{6}$ 와 중복 없음 · 보통주(끝자리 0) · market ∈ KOSPI/KOSDAQ ·
      sector_l1 비어 있지 않음
"""
import csv
import re
import sys
from collections import Counter

path = sys.argv[1]
rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
errors: list[str] = []

if len(rows) != 100:
    errors.append(f"행 수 {len(rows)} (100이어야 함)")
tickers = [r["ticker"] for r in rows]
if len(set(tickers)) != len(tickers):
    errors.append("ticker 중복")
for r in rows:
    if not re.fullmatch(r"[0-9A-Z]{6}", r["ticker"]):
        errors.append(f"{r['ticker']}: ticker 형식")
    if not r["ticker"].endswith("0"):
        errors.append(f"{r['ticker']} {r['name']}: 끝자리가 0이 아님(파이프라인은 우선주로 취급)")
    if r["market"] not in ("KOSPI", "KOSDAQ"):
        errors.append(f"{r['ticker']}: market={r['market']}")
    if not r["sector_l1"]:
        errors.append(f"{r['ticker']} {r['name']}: sector_l1 비어 있음")

print(f"{path}: {len(rows)}종목", dict(Counter(r["market"] for r in rows)))
print("sector_l1:", dict(Counter(r["sector_l1"] for r in rows)))
if errors:
    print("검증 실패:", *errors, sep="\n  - ")
    sys.exit(1)
print("검증 통과")
