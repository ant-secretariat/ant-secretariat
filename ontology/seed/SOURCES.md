# 온톨로지 관계사전 시드 v0.4 — 값의 출처와 결정 근거

작성: 유민 · 2026-11-10 (v0.2 2026-11-09) · 기준 스펙: 온톨로지 프로덕트 기획서 v1.2

이 문서는 시드에 채워진 값이 **어디서 왔고, 어떤 규칙으로 정했고, 얼마나 검증됐는지**를 항목별로 정리한다.
JSON 레코드에도 `*_source` / `status` / `inactive_reason` / `pipeline_status` / `weight_status` 필드로 같은 정보가 들어 있다.

v0.4는 v0.3에 "수집 계획 없는 매크로는 삭제하지 않고 비활성 보관" 결정(유민)을 반영한 버전이다(6번 SENSITIVE_TO). v0.3은 수경(nasuzz) 데이터 파이프라인의 실제 코드·답변(2026-11-10)과 대조해 맞춘 버전이다. 파이프라인 값으로 바꾼 항목은 검증 상태를 ✅로 올리고 출처에 파일 경로를 적었다. 파이프라인 코드 경로는 PR #10~#19(open) 기준이다.

## 0. 한눈에 보기

| # | 항목 | 값의 출처 | 결정 방식 | 검증 상태 |
|---|---|---|---|---|
| 1 | T1 종목 100개 | 수경 파이프라인 `companies.is_core` (`core_companies_2026-11-09.csv`, 코드 `data-pipeline/crawling/market_loader.py::_assign_core`) | 파이프라인 값 그대로 | ✅ 실데이터 (2026-10-22 지정 후 고정) |
| 2 | 종목 → 섹터 배정 | `companies.sector_l1` WICS 대분류 (`data-pipeline/crawling/collectors/wics_collector.py`, `market_loader.py::refresh_sectors`) | 파이프라인 값 그대로 (v0.2 초안 7종목 교체) | ✅ 실데이터 |
| 3 | 지주사 여부·세부 산업 | 도메인 지식 | 수작업 (섹터 상속 보정용) | ⚠️ 초안 |
| 4 | 섹터 속성 (cycle/rate/fx) | GICS 섹터 일반론 + 한국 시장 구조 | 정성 판단 | ⚠️ 초안 · 회귀 결과로 검증 예정 |
| 5 | 매크로 지표 7개 (수집 중) | `data-pipeline/crawling/collectors/macro_data_collector.py::DEFAULT_ECOS_INDICATORS`, `index_daily` | 파이프라인 ID·항목코드 그대로 | ✅ 실코드 |
| 6 | 매크로 지표 7개 (수집 계획 없음) | FRED·ECOS·NBS·TrendForce 후보 | 아젠다 경로상 필요한 지표 → `status: inactive`로 보관 | ⚠️ 수경 "수집 계획 없음" (2026-11-10) · 비활성 |
| 7 | ISSUE 26개 | 업종 구조·정책 이슈 (도메인 지식) | 선정 기준 3개로 필터링 | ⚠️ 초안 · 근거 청크 미연결 |
| 8 | BENEFITS/HURTS strength | 매출 노출도에 대한 정성 판단 | low / mid / high 3단계 | ⚠️ 초안 |
| 9 | EXPOSED_TO exposure | strength 기계적 변환 | high .9 / mid .6 / low .3 | ⚠️ 초안 |
| 10 | SENSITIVE_TO 엣지 쌍 28개 (활성 19 · 비활성 9) | 섹터 속성 + 원가·수요 경로 | 경제적 전달 경로 가설. BASE_RATE_KR 3개는 KTB_3Y_KR로 합침 | ⚠️ 초안 |
| 11 | SENSITIVE_TO weight | 비어 있음 (null) | 수경 `sensitivities.corr_daily` 섹터 집계로만 채움 | — 대기 (활성 19개: `aggregation_pending` 11 · `factor_requested` 8) |
| 12 | SENSITIVE_TO expected_sign | 경제적 전달 경로 | 부호 가설 (+ / − / ±) | ⚠️ 회귀 부호와 대조용 |
| 13 | IMPACTS (매크로→매크로) | 표준 거시 전달 경로 | 방향(same/opposite)만 정의 | ⚠️ 교과서적 관계 · 미검증 |

**검증 상태 요약: ✅ 3 · ⚠️ 9 · 대기 1** (13개 항목, v0.3과 같음). ✅는 파이프라인 값으로 교체된 항목이다. v0.4는 항목 수를 바꾸지 않고 6·10·11번의 처리 방식만 정했다.

---

## 1. T1 종목 (`nodes/companies_t1.json`) — ✅

**출처.** 수경 Supabase `companies` 테이블에서 `is_core = true`인 종목을 내보낸 `core_companies_2026-11-09.csv`(100행, 컬럼 `ticker,name,market,sector_l1,sector_l2`). 입력 CSV는 시드 재현용 마스터 목록이며 시세·리포트 같은 수집 원본이 아니다.

**파이프라인의 T1 정의 (코드와 수경 답변 2026-11-10).**
1. 시장 = KOSPI + KOSDAQ 통합(`pykrx get_market_cap(market="ALL")`) 시가총액 상위 100
2. 우선주 제외 — `is_preferred = not ticker.endswith("0")`
3. 2026-10-22에 시가총액 순위로 **한 번 지정**하고 이후 고정 (`is_core`, 재산정·강등 없음)
4. 현재 구성 KOSPI 90 + KOSDAQ 10

**v0.2(KOSPI 시총 상위 100, 2026-11-05)와의 차이.** 90종목은 같고 10종목이 바뀌었다.

| 구분 | 종목 |
|---|---|
| 추가 (KOSDAQ 10) | 삼천당제약 000250, HLB 028300, 주성엔지니어링 036930, 이오테크닉스 039030, 리노공업 058470, 에코프로 086520, 알테오젠 196170, 원익IPS 240810, 에코프로비엠 247540, 레인보우로보틱스 277810 |
| 제외 (v0.2 시총 84~99위) | 삼성카드 029780, NC 036570, 맥쿼리인프라 088980, 한미약품 128940, BNK금융지주 138930, JB금융지주 175330, 두산밥캣 241560, HD건설기계 267270, 오리온 271560, 카카오페이 377300 |

- 제외 종목에 걸려 있던 이슈 엣지 2개는 버렸다 (`ISS_PLATFORM_REGULATION`→카카오페이, `ISS_KFOOD_EXPORT`→오리온). `meta.dropped_issue_edges`에 남겨 두었다.
- **추가한 KOSDAQ 10종목에는 이슈 엣지가 없다** (BELONGS_TO만). 이슈 라벨링 필요 — ⚠️ 후속.
- 필드: `market_cap_tier` → `tier`로 이름을 바꾸고(파이프라인 컬럼명), `market`, `is_core`, `tier_assigned_on`을 추가했다. 외부 데이터셋 기반이던 `marcap_rank`·`rank_as_of`는 삭제했다.
- 삼성에피스홀딩스(0126Z0)는 신규 상장이라 거래일 수(250일)가 모자라 파이프라인 `sensitivities`에는 없다. T1에는 포함이다.

## 2. 종목 → 섹터 배정 (`sector_id`, `sector_source: pipeline`) — ✅

**출처.** `companies.sector_l1`(WICS 대분류 10개, 중분류는 `sector_l2`로 같이 저장). v0.2의 GICS 관행 수작업 배정(`claude_draft`)을 **WICS 값으로 교체**했다. WICS 코드가 GICS 번호 체계와 같아 `sectors.json`의 `gics_code`로 매핑된다(`wics_code = "G" + gics_code`).

**교체된 종목 (v0.2와 불일치, 90종목 중 7).**

| 종목 | v0.2 | v0.3 (WICS) | WICS 중분류 |
|---|---|---|---|
| 삼성SDI | 산업재 | IT | 전자와 전기제품 |
| LG에너지솔루션 | 산업재 | IT | 전자와 전기제품 |
| LG전자 | 경기소비재 | IT | 전자와 전기제품 |
| 한화솔루션 | 소재 | 에너지 | 에너지 |
| SK | 산업재(지주) | 에너지 | 에너지 |
| 아모레퍼시픽 | 필수소비재 | 경기소비재 | 내구소비재와의류 |
| 에이피알 | 필수소비재 | 경기소비재 | 내구소비재와의류 |

**섹터 노드 변경.** `SEC_REAL_ESTATE`를 삭제했다. WICS 대분류에는 부동산이 없고(중분류가 금융 아래 G4050), 소속 종목도 0개였다. 걸려 있던 SENSITIVE_TO 엣지(부동산→KTB_10Y_KR) 1개도 같이 삭제했다. 시드 섹터는 11개 → 10개다.

**남은 한계.** 산업재가 31개로 여전히 크다 (조선·방산·전력기기·건설·운송·지주). 섹터 단위 민감도는 이 안의 차이를 못 잡아서 `sub_industry`를 따로 달았다. `is_holding`·`sub_industry`는 Claude 초안(`sub_industry_source`) — ⚠️.

## 3. 섹터 속성 (`nodes/sectors.json`) — ⚠️

정성 판단이다. 이번 대조에서 바뀐 것은 없고 `wics_code`·`wics_name`만 추가했다.

| 속성 | 값 | 기준 |
|---|---|---|
| `cycle_type` | defensive / growth / cyclical | GICS 일반론. 필수소비재·헬스케어·유틸리티 = defensive, IT·커뮤니케이션 = growth, 나머지 = cyclical |
| `rate_sensitivity` | high / medium / low | high = 먼 미래 현금흐름 비중이 큰 성장주, 채권 대체재(유틸리티). low = 필수소비재·에너지 |
| `fx_sensitivity` | positive / negative / neutral | 원화 약세(USD/KRW 상승) 시 이익 방향. 수출 비중 큰 섹터 = positive, 원재료·연료 수입 의존 = negative, 혼재 = neutral |

**검증 계획.** 수경의 섹터별 corr_daily 집계가 오면 부호·크기로 이 라벨을 확인한다. 어긋나면 라벨을 고친다 (라벨이 회귀 값을 덮어쓰지 않는다). WICS 재분류로 섹터 구성이 바뀐 만큼(위 7종목) 라벨 재점검이 필요하다.

## 4. 매크로 지표 (`nodes/macros.json`)

수경 파이프라인은 **ECOS만** 수집하고 FRED·NBS·TrendForce 수집기는 없다. 시드 각 지표에 `pipeline_status`(collecting / not_planned), `pipeline_table`, `pipeline_key`, `pipeline_item_code`를 추가했다.

**수집 중 7개 — ✅ (ID·항목코드는 파이프라인 값)**

| indicator_id | 테이블 | 키 / ECOS 항목코드 | 주기 | 비고 |
|---|---|---|---|---|
| BASE_RATE_KR | `macro_data` | 722Y001 / 0101000 | daily | v0.2는 `event`였으나 파이프라인이 일별 저장 |
| KTB_3Y_KR | `macro_data` | 817Y002 / 010200000 | daily | 민감도 요인 |
| KTB_10Y_KR | `macro_data` | 817Y002 / 010210000 | daily | |
| USD_KRW | `macro_data` | 731Y001 / 0000001 | daily | 민감도 요인 |
| CPI_KR | `macro_data` | 901Y009 / 0 | monthly | |
| BRENT | `macro_data` | 902Y003 / 010103 | monthly | v0.2 `OIL_BRENT`(FRED 일별)에서 변경. **ECOS 월평균** |
| KOSPI | `index_daily` | index_code `1001` | daily | v0.2 `KOSPI_INDEX`에서 변경. `macro_data`가 아니라 `index_daily`. 민감도 요인명도 `KOSPI` |

**수집 계획 없음 7개 — ⚠️ 비활성 보관 (수경 2026-11-10: "FRED 지표는 아직 수집 계획에 없음")**
`US_FFR`, `US_10Y_YIELD`, `USD_CNY`, `VIX`(FRED), `PPI_KR`(ECOS 코드 미확인), `CHINA_PMI_MFG`(NBS), `DRAM_PRICE`(TrendForce, 유료).
- 결정(유민, 중간안): **삭제하지 않고** 매크로와 거기 걸린 엣지에 `status: "inactive"`, `inactive_reason: "no_data_source"`를 단다. 삭제하면 아젠다 경로 설계가 사라지고, 그대로 두면 데이터 없는 근거 없는 주장이 주입되기 때문이다.
- 비활성은 `get_ontology_context` 주입과 Judge 경로 검증에서 뺀다. 데이터 수집이 생기면 `status`만 `active`로 바꾸면 된다 (기획서의 off → shadow → on 구조와 같은 방식).
- 헬퍼(`ontology_seed.py`)의 `active_edges()` · `active_macros()` · `company_context()`는 활성만 돌려준다. 비활성이 필요하면 `company_context(include_inactive=True)`.
- 후속: **`DRAM_PRICE`는 SEC_IT(삼성전자·SK하이닉스 시총 1·2위) 핵심 경로**라 무료 대체 지표를 우선 찾아야 한다 (수경에게 질문).

**참고.** 파이프라인에는 시드에 없는 `WTI`, `DUBAI`, `EXPORTS_KR`, `IMPORTS_KR`, `IPI_KR`, 계산 지표 `TRADE_BALANCE_KR`도 이미 있다. 수출 비중이 큰 섹터 엣지의 후보지만, 근거 없이 넣지 않았다.

**스펙과 다른 점.** `category` 예시값(rate / fx / commodity / market)에 `inflation`, `sentiment` 두 개를 추가했다. 승인 필요. 파이프라인 `macro_data`에는 category 컬럼이 없으므로 category는 온톨로지 쪽 속성이다.

## 5. ISSUE 26개 (`nodes/issues.json`, `status: draft`) — ⚠️

**선정 기준 (셋 다 충족).**
1. T1 종목 1개 이상에 영향을 주는 경로를 한 문장으로 설명할 수 있다
2. 하루짜리 뉴스가 아니라 지속되거나 반복되는 이슈다
3. Bull과 Bear 양쪽 논거로 쓸 수 있다

**값의 의미.** `polarity`는 연결된 종목·섹터 입장에서의 방향(positive → BENEFITS, negative → HURTS). `strength`는 매출·이익 영향 비중에 대한 정성 판단(high = 핵심 사업 직결, mid = 주요 사업 일부, low = 간접). `duration`은 persistent / cyclical / event_driven이고 `review_cycle_days`(180 / 90 / 30)는 재검토 주기 제안값이다.

**근거 청크 — 아직 연결 안 됨 (v1.2 필수 속성).** `evidence_chunk_ids`, `valid_from` / `valid_until`이 비어 있다. 수경 답변(2026-11-10)으로 연결 방법은 확정됐다.
- 벡터 저장소는 Supabase **pgvector**로 이전됐다 (v0.2 조사 시점 코드에는 Pinecone).
- 리포트 94종목 (2026-08-07 ~ 11-06, 활성 청크 17,272개) · 뉴스 98종목 (기사 6,822건, 청크 11,576개, 최근 2주 위주) · 공시는 적재 진행 중.
- `chunk_id`는 내용 기준이라 재적재해도 같다. 청킹 규칙이 바뀌어 사라진 청크는 삭제하지 않고 `is_active=false`로 남기므로 예전 id로 찾아도 깨지지 않는다. 뉴스 id는 원문 URL 기준이다.
- 따라서 `evidence_chunk_ids`에는 `chunk_id`를 저장하고, `valid_from`은 근거 청크 날짜, `valid_until`은 `review_cycle_days`로 정한다. DB 조회 권한이 필요해 이번 PR에서는 비워 두었다.

**확정 규칙 제안.** 근거 청크를 1개 이상 못 찾은 이슈는 시드에서 뺀다. 이 규칙을 통과해야 `status: draft` → `confirmed`. 뉴스가 최근 2주 위주라 오래된 `persistent` 이슈는 리포트 청크로 근거를 찾아야 할 수 있다.

## 6. 엣지

### BELONGS_TO (COMPANY → SECTOR, 100개) — ✅
종목 → 섹터 배정(2번, 파이프라인 값)에서 기계적으로 생성.

### BENEFITS / HURTS (ISSUE → COMPANY 또는 SECTOR, 98개) — ⚠️
ISSUE 정의에 포함된 대상 목록에서 생성. v0.2의 100개에서 **제외된 종목 대상 2개를 버렸다**. 섹터 단위 엣지는 해당 섹터 전체에 영향이 고른 경우에만 걸었고, 같은 이슈가 섹터와 종목 둘 다에 걸리면 종목 엣지를 우선한다. 추가된 KOSDAQ 10종목에는 엣지가 없다.

### EXPOSED_TO (COMPANY → ISSUE, 93개) — ⚠️
BENEFITS/HURTS 중 종목 대상 엣지를 뒤집고 `strength`를 숫자로 바꿨다 (high 0.9 / mid 0.6 / low 0.3). 독립적으로 판단한 값이 아니므로 `exposure_source`에 변환 규칙을 적어뒀다. 매출 비중 데이터가 생기면 교체한다.

### SENSITIVE_TO (SECTOR → MACRO, 28개: 활성 19 · 비활성 9) — weight 대기
- **weight는 전부 null.** 수경의 회귀 결과를 받기 전에는 채우지 않는다. 전문가 정의 값으로 채우지 않는다.
- **수경 파이프라인의 회귀** (`data-pipeline/crawling/analytics/sensitivity.py`, 테이블 `sensitivities`):
  - 종목 단위, 요인 3개(`KOSPI`, `USD_KRW`, `KTB_3Y_KR`), 최근 3년, 30일 수익률
  - 기획서 v1.2의 "일별 수익률 표준화 계수(상관 기반 민감도)"에 해당하는 컬럼은 **`corr_daily`**다. `beta`(30일 겹침 구간·요인 1σ당 %)는 다른 값이다.
- **섹터 값은 수경이 집계해 준다** (2026-11-10): 섹터별 `corr_daily` **중앙값 + 종목 수**, 최신 `as_of` 기준(2026-11-06). 시장 지수 3개만 받고 있고 KRX 업종지수는 WICS와 분류가 달라 소속 종목 값을 묶는 방식으로 한다.
- **원인별 분류 (v0.3의 29개 중 `none_planned` 20개 + `planned` 9개)** — 결정은 유민(중간안: ① 복구 + ② 비활성 보관)

| 분류 | 처리 | 엣지 | 수 |
|---|---|---|---|
| A. 회귀 요인에 있음 | `weight_status: aggregation_pending` (수경 집계 대기) | `USD_KRW` 7 · `KOSPI` 1 · `KTB_3Y_KR` 1 (FIN) | 9 |
| B. 기준금리 → KTB_3Y_KR 합침 | 아래 별도 설명. 합친 뒤 A와 같이 `aggregation_pending` | SEC_IT·SEC_CONS_DISC는 `BASE_RATE_KR`을 `KTB_3Y_KR`로 교체, SEC_FIN은 이미 `KTB_3Y_KR`이 있어 중복 제거 | 3 → 2 |
| C. 수집 중이나 회귀 요인 아님 | `weight_status: factor_requested` | `KTB_10Y_KR` 3 (COMM·HEALTH·UTIL, 일별) · `CPI_KR` 1 (CONS_DISC, 월별) · `BRENT` 4 (INDUS·MATERIAL·ENERGY·UTIL, 월별) | 8 |
| D. 수집 계획 없는 매크로 | `status: inactive`, `inactive_reason: no_data_source`, `weight_status: null` | SEC_IT: `US_10Y_YIELD`·`DRAM_PRICE`·`VIX` / CONS_DISC: `CHINA_PMI_MFG` / CONS_STAP: `PPI_KR` / FIN: `VIX` / INDUS: `CHINA_PMI_MFG` / MATERIAL: `CHINA_PMI_MFG`·`USD_CNY` | 9 |

  v0.3의 `none_planned` 20 = B 3 + C 8 + D 9. 합치고 나면 총 28개 = A 9 + B 2 + C 8 + D 9 (활성 19 = A + B + C).
- **BASE_RATE_KR 합침.** 기준금리는 일별로 저장되지만 정책 결정일에만 바뀌는 계단식 값이라 일별 수익률과의 상관이 의미 없다. 같은 방향의 금리 가설을 `KTB_3Y_KR`(시장이 기준금리 기대를 반영하는 단기 금리)로 옮긴다. 합친 엣지에는 `merged_from: ["BASE_RATE_KR"]`을 남겼고 `meta.merged_sensitive_edges`에 3건의 처리(renamed 2, dedup 1)와 원래 `expected_sign`이 있다. SEC_FIN은 둘 다 `+`라 충돌이 없었다. `BASE_RATE_KR` 노드와 IMPACTS 엣지는 그대로 둔다.
- **`weight_frequency`.** C 중 `CPI_KR`·`BRENT`는 월별이라 일별 `corr_daily`로는 못 구한다. 월별 상관을 따로 산출할 수 있는지는 수경에게 질문한다. `KTB_10Y_KR`는 일별이라 회귀 요인에 추가만 하면 된다.
- 채울 때 함께 넣을 필드: `weight_source`(예: `sensitivities.corr_daily sector median`), `weight_window`(`window_start`~`as_of`), `weight_as_of`, `weight_n_tickers`(집계에 쓴 종목 수). `build_seed.py`는 `weight_source` 없이 weight를 채우면 실패한다.
- **expected_sign:** 회귀 결과 부호 검증용 사전 가설이다. 회귀 부호가 가설과 다르면 자동으로 덮어쓰지 않고 검토 목록에 올린다. weight 대용으로 쓰지 않는다. 수경 `direction_uncertain`(신뢰구간이 0 포함)도 함께 본다.
- 삭제: `SEC_REAL_ESTATE → KTB_10Y_KR` (섹터 삭제, 2번 참고).

### IMPACTS (MACRO → MACRO, 15개: 활성 5 · 비활성 10) — ⚠️
끝점 중 하나라도 수집 계획 없는 매크로면 `status: inactive`(`inactive_macros`에 해당 지표). 활성 5개는 `BASE_RATE_KR→KTB_3Y_KR`·`BASE_RATE_KR→KTB_10Y_KR`·`BASE_RATE_KR→USD_KRW`·`USD_KRW→CPI_KR`·`CPI_KR→BASE_RATE_KR`.

표준 거시 전달 경로(정책금리 → 시장금리, 금리차 → 환율, 유가 → PPI → CPI, 위험회피 → 원화 약세 등). 스펙상 IMPACTS는 방향만 명시하므로 `relation`(same / opposite)만 두고 weight는 없다. ID만 파이프라인 이름으로 바꿨다(`BRENT`, `KOSPI`).

### COMPETES_WITH
만들지 않았다. COMPETITOR 노드를 COMPANY로 합칠지(유민 제안)가 미결이다.

## 7. 재현 방법

```bash
python scripts/extract_t1.py core_companies_2026-11-09.csv   # CSV 형식 검증
python scripts/build_seed.py core_companies_2026-11-09.csv .  # 시드 생성 + 무결성 검사
```

`build_seed.py`는 정의 데이터(이슈, 엣지 쌍)를 코드 안에 담고 있고 표준 라이브러리만 쓴다. 실행하면 `nodes/`·`edges/`·`ontology_seed_all.json`·`ontology_seed.py`를 다시 쓰며, 같은 입력이면 결과가 같다. 무결성 검사: 종목 100개·중복 없음, 엣지 양 끝 노드 존재, 이슈·지표 ID 중복 없음, 소속 종목 없는 섹터 없음, 출처 없는 weight 금지, 비활성 매크로에 걸린 엣지는 반드시 비활성(그 반대도), 활성 엣지의 `weight_status`는 값이 있고 비활성은 없음, SENSITIVE_TO 쌍 중복 없음.

## 8. 팀원 확인 요청

| 누구 | 무엇 | 상태 |
|---|---|---|
| 수경 | 섹터별 `corr_daily` 중앙값 + 종목 수 집계 전달 (최신 as_of 2026-11-06) | 대기 (수경 집계 예정) |
| 수경 | `KTB_10Y_KR`를 회귀 요인에 추가 가능한지 (일별) | 질문 전달 대기 |
| 수경 | `CPI_KR`·`BRENT`(월별)를 월별 상관으로 따로 산출 가능한지 | 질문 전달 대기 |
| 수경 | `DRAM_PRICE` 무료 대체 지표 아이디어 (삼성전자·SK하이닉스 핵심 경로) | 질문 전달 대기 |
| 유민 | 수집 계획 없는 지표 7개 | ✅ 결정: 삭제 않고 `inactive` 보관 (v0.4) |
| 유민 | KOSDAQ 신규 10종목의 이슈 엣지 라벨링, `is_holding`·`sub_industry` 검토 | 후속 |
| 태은 | Supabase 테이블로 옮길 때 이 JSON 구조 그대로 써도 되는지 · `company_context` 2홉 헬퍼가 `get_ontology_context` 구현과 겹치는지 | 미회신 |
| 전원 | MACRO category 2개 추가 승인 · ISSUE 확정 규칙(근거 청크 1개 이상) 승인 · COMPETITOR 통합 결정 | 미결 |

## 9. 계약 메모 (수경 답변 2026-11-10)

- 시드의 `agenda_ids`는 `valuation / macro / risk / growth / shareholder_return` 값이고 토론 패키지 임시 `AgendaId`와 같다. 수경이 data-pipeline에 공용 열거형을 만들 계획이라 만들어지면 import로 바꾼다.
- 종목 등급은 `tier`(T0 / T1 / T2)이고 `resolve_company`가 `tier`와 `data_status`를 돌려줄 예정이다. `data_tier`(report / news_only / disclosure_only / derived_only / macro_only)는 `get_agent_context` 결과에 들어간다. 시드 COMPANY의 `tier`는 앞의 것이다.
- ticker 형식은 파이프라인 `^[0-9A-Z]{6}$`이고 시드 100개 전부 통과한다 (`0126Z0` 포함).

## 10. 변경 이력

| 버전 | 날짜 | 변경 |
|---|---|---|
| v0.2 | 2026-11-09 | 최초 시드. KOSPI 시총 상위 100(marcap), GICS 관행 섹터 배정, 매크로 14개 |
| v0.3 | 2026-11-10 | 수경 파이프라인 대조. T1 = core 100(KOSPI 90 + KOSDAQ 10), 섹터 = WICS, 매크로 ID 통일(`BRENT`, `KOSPI`)·수집 상태 필드, `SEC_REAL_ESTATE` 삭제, SENSITIVE_TO `weight_coverage`·`weight_n_tickers` 추가 |
| v0.4 | 2026-11-10 | 수집 계획 없는 매크로 7개와 엣지(SENSITIVE_TO 9·IMPACTS 10) `inactive` 보관, BASE_RATE_KR 대상 SENSITIVE_TO 3개 → KTB_3Y_KR 합침(29→28), `weight_coverage`를 `weight_status`(aggregation_pending / factor_requested)·`weight_frequency`로 대체, 헬퍼에 active 필터 추가 |
