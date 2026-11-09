# get_financials · get_market_snapshot

API 계약서(`docs/api/openapi.yaml`)의 `get_financials`, `get_market_snapshot`(출력 `DataRecord`)입니다. 둘 다 Supabase를 읽고(`SUPABASE_DB_URL` 필요), 조회가 실패해도 예외 대신 빈 결과와 `error`를 돌려줍니다.

## get_financials(ticker, period_type="quarter", date_from=None, date_to=None, as_of=None)

OpenDART 주요계정(`financials`)을 **공시 접수일 기준**으로 읽습니다. `as_of`(기본 오늘)까지 접수된 공시만 쓰고, 정정공시가 있으면 그날까지 접수된 가장 최근 것을 씁니다. 그래서 5/15에 공시된 실적은 5/14 기준 조회에 보이지 않습니다.

```python
from processing.functions.get_financials import get_financials

get_financials("000660")                              # 분기, 최신 분기부터
get_financials("000660", period_type="annual")        # 연간 (4분기 공시가 있는 연도만)
get_financials("000660", as_of="2026-08-13")          # 8/13까지 공시된 것만 → 최신이 2026Q1
get_financials("005930", date_from="2025-01-01", date_to="2025-12-31")  # 기간 말일 기준
```

```json
{
  "ticker": "000660", "company": "SK하이닉스", "period_type": "quarter", "as_of": "2026-11-10",
  "unit": "원", "basis": "공시 접수일 기준, 연결 우선(없으면 별도)",
  "records": [
    {"period": "2026Q2", "fiscal_year": 2026, "quarter": 2, "period_end": "2026-06-30", "fs_div": "연결",
     "disclosed_at": "2026-08-14", "rcept_no": "...",
     "revenue": 79318746000000, "operating_income": 60542608000000, "pretax_income": 0, "net_income": 0,
     "total_assets": 0, "current_assets": 0, "noncurrent_assets": 0, "total_liabilities": 0,
     "current_liabilities": 0, "noncurrent_liabilities": 0, "total_equity": 262693228000000,
     "capital_stock": 0, "retained_earnings": 0, "operating_margin": 76.33, "debt_ratio": 32.8}
  ]
}
```

- 기간마다 연결(CFS)이 있으면 연결, 없으면 별도(OFS). `fs_div`에 어느 쪽인지 표시
- 분기: 손익은 그 분기 3개월 값(4분기 단독은 연간 − 3분기 누적), 재무상태표는 분기말 잔액
- 연간: 손익은 연간 누적, 재무상태표는 연말 잔액
- 은행·증권·보험(WICS 금융)은 `get_metric`과 같이 `debt_ratio`를 `null`로 두고 `debt_ratio_note: "not_applicable_financials"`. 금융업은 `revenue`가 없을 수 있음
- 현재 T1 100개 종목, 2023년부터 적재되어 있음. 3분기 실적은 11/14 공시 후 적재
- `period_type`이 `quarter`·`annual`이 아니면 `"error": "unsupported_period_type"`

## get_market_snapshot(sector=None, top_n=20, sort_by="market_cap", as_of=None)

그날(`as_of`, 기본 오늘)까지의 가장 최근 거래일 시세와 일별 지표로 종목 순위를 냅니다.

```python
from processing.functions.get_market_snapshot import get_market_snapshot

get_market_snapshot()                                          # 시가총액 상위 20
get_market_snapshot(sector="반도체와반도체장비", top_n=5)        # WICS 중분류
get_market_snapshot(sector="금융", sort_by="pbr", top_n=5)       # WICS 대분류, PBR 낮은 순
get_market_snapshot(sort_by="change_pct", as_of="2026-10-15")  # 그날 등락률 높은 순
```

```json
{
  "as_of": "2026-11-06", "requested_as_of": "2026-11-10", "sector": null, "sort_by": "market_cap", "order": "desc",
  "universe": "시세가 적재된 종목(현재 T1)", "count": 20,
  "companies": [
    {"rank": 1, "ticker": "005930", "company": "삼성전자", "market": "KOSPI", "sector_l1": "IT",
     "sector_l2": "반도체와반도체장비", "close": 0, "change_pct": 0, "volume": 0, "trading_value": 0,
     "market_cap": 1103192773329600, "per": 0, "pbr": 0, "dividend_yield": 0, "foreign_ratio": 0}
  ]
}
```

- `sector`: WICS 대분류(`sector_l1`) 또는 중분류(`sector_l2`) 이름. 없는 이름이면 `"error": "unknown_sector"`
- `sort_by`: `market_cap`, `trading_value`, `volume`, `change_pct`(전 거래일 대비 %), `dividend_yield`는 큰 순, `per`, `pbr`은 작은 순(0 이하는 뺌). 그 밖은 `"error": "unsupported_sort_by"`
- `top_n`은 1~100. 우선주는 뺌
- 대상은 시세가 적재된 종목뿐(현재 T1 100개). 기획서의 T0 전 종목 시세를 적재하면 같은 코드로 전 종목이 됨
