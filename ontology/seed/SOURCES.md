# 온톨로지 관계사전 시드 v0.9 — 값의 출처와 결정 근거

작성: 유민 · 2026-11-10 (v0.2 2026-11-09) · 기준 스펙: 온톨로지 프로덕트 기획서 v1.2

이 문서는 시드에 채워진 값이 **어디서 왔고, 어떤 규칙으로 정했고, 얼마나 검증됐는지**를 항목별로 정리한다.
JSON 레코드에도 `*_source` / `status` / `inactive_reason` / `pipeline_status` / `weight_status` 필드로 같은 정보가 들어 있다.

v0.9는 종목 → 매크로 SENSITIVE_TO 10개를 추가한 버전이다(#56, 시장 효과를 뺀 종목 단위 값). v0.8은 수경 온톨로지 입력값(이슈 #61, 계산 코드 PR #62, 기준일 2026-11-23)을 반영해 데이터와 초안이 같은 매크로 방향 4개·IMPACTS 1개를 확정하고, 지주사·세부 업종을 KRX KIND 후보로 확정한 버전이다. 섹터 금리·환율 등급은 계속 초안이다. v0.7은 수경 검증(PR #29 코멘트 2026-11-23)을 반영해 가설과 어긋난 SENSITIVE_TO 9개를 기각(`rejected`)하고, 시장 효과를 빼지 않은 상관은 노출하지 않도록 바꾼 버전이다. 대신 모든 섹터에 → `KOSPI`(시장 동조) 엣지를 두어, 노출되는 SENSITIVE_TO는 KOSPI 엣지 8개다. 이어서 수경이 보류 10개의 시장 효과를 뺀 값을 냈고(이슈 #56), 10개 모두 기준 미달이라 기각했다(기각 19개). v0.6은 태은 리뷰(PR #29)를 반영해 노출 규칙을 바꾼 버전이다. 노출 = `status == "active"` 이고 `reviewed == true` 인 노드·엣지만이며(ADR 0008), Claude 초안과 가설과 어긋난 민감도는 기본값에서 빠진다. 원본은 `ontology_seed.json` 하나이고 `ontology_seed.py`는 손으로 쓴 로더다. v0.5는 수경이 PR #29에 남긴 섹터별 weight·DRAM 대체 지표·`KTB_10Y_KR` 답변(2026-11-10, 값은 PR #34 기준)을 반영해 weight를 채운 버전이다. v0.4는 v0.3에 "수집 계획 없는 매크로는 삭제하지 않고 비활성 보관" 결정(유민)을 반영한 버전이다(6번 SENSITIVE_TO). v0.3은 수경(nasuzz) 데이터 파이프라인의 실제 코드·답변(2026-11-10)과 대조해 맞춘 버전이다. 파이프라인 값으로 바꾼 항목은 검증 상태를 ✅로 올리고 출처에 파일 경로를 적었다. 파이프라인 코드 경로는 PR #10~#19(open) 기준이다.

## 0. 한눈에 보기

| # | 항목 | 값의 출처 | 결정 방식 | 검증 상태 |
|---|---|---|---|---|
| 1 | T1 종목 100개 | 수경 파이프라인 `companies.is_core` (`core_companies_2026-11-09.csv`, 코드 `data-pipeline/crawling/market_loader.py::_assign_core`) | 파이프라인 값 그대로 | ✅ 실데이터 (2026-10-22 지정 후 고정) |
| 2 | 종목 → 섹터 배정 | `companies.sector_l1` WICS 대분류 (`data-pipeline/crawling/collectors/wics_collector.py`, `market_loader.py::refresh_sectors`) | 파이프라인 값 그대로 (v0.2 초안 7종목 교체) | ✅ 실데이터 |
| 3 | 지주사 여부·세부 산업 | 도메인 지식 | 수작업 (섹터 상속 보정용) | ⚠️ 초안 |
| 4 | 섹터 속성 (cycle/rate/fx) | GICS 섹터 일반론 + 한국 시장 구조 | 정성 판단 | ⚠️ 초안 · 회귀 결과로 검증 예정 |
| 5 | 매크로 지표 8개 (수집 중) | `data-pipeline/crawling/collectors/macro_data_collector.py::DEFAULT_ECOS_INDICATORS`, `index_daily` | 파이프라인 ID·항목코드 그대로 | ✅ 실코드 |
| 6 | 매크로 지표 6개 (수집 계획 없음) | FRED·ECOS·NBS 후보 | 아젠다 경로상 필요한 지표 → `status: inactive`로 보관 | ⚠️ 수경 "수집 계획 없음" (2026-11-10) · 비활성 |
| 7 | ISSUE 26개 | 업종 구조·정책 이슈 (도메인 지식) | 선정 기준 3개로 필터링 | ⚠️ 초안 · 근거 청크 미연결 |
| 8 | BENEFITS/HURTS strength | 매출 노출도에 대한 정성 판단 | low / mid / high 3단계 | ⚠️ 초안 |
| 9 | EXPOSED_TO exposure | strength 기계적 변환 | high .9 / mid .6 / low .3 | ⚠️ 초안 |
| 10 | SENSITIVE_TO 엣지 쌍 28개 (활성 20 · 비활성 8) | 섹터 속성 + 원가·수요 경로 | 경제적 전달 경로 가설. BASE_RATE_KR 3개는 KTB_3Y_KR로 합침 | ⚠️ 초안 |
| 11 | SENSITIVE_TO weight | 수경 섹터 중앙값 (일별 `corr_daily_median` · 월별 `corr_monthly_median`) | 수경 값 그대로 (활성 20개 모두 채움, 비활성 8개는 null) | ✅ 수경 DB 값 (PR #34 미병합 기준) |
| 12 | SENSITIVE_TO expected_sign | 경제적 전달 경로 | 부호 가설 (+ / − / ±) | ⚠️ 회귀 부호와 대조용 |
| 13 | IMPACTS (매크로→매크로) | 표준 거시 전달 경로 | 방향(same/opposite)만 정의 | ⚠️ 교과서적 관계 · 미검증 |

**검증 상태 요약: ✅ 4 · ⚠️ 9 · 대기 0** (13개 항목). ✅는 파이프라인 값으로 교체된 항목이다(v0.5에서 11번 weight 추가). 부호 검증(`expected_sign`)과 ISSUE 근거 청크는 ⚠️로 남아 있다.

---

## 1. T1 종목 (`nodes.companies_t1`) — ✅

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
- **v0.8 (#61): 지주사·세부 업종 확정.** KRX KIND 상장법인목록(100종목 모두 있음)의 업종·주요제품으로 수경이 낸 후보를 유민이 검토했다.
  - `is_holding`은 100종목 모두 검토 끝(노출). `holding_type`: legal(KIND로 확인한 지주회사 8: LG·POSCO홀딩스·삼성에피스홀딩스·SK·GS·한진칼·HD현대·SK스퀘어), financial(금융지주 6: KB금융·신한·한국금융·하나·메리츠·우리. KB금융은 KIND 이름 규칙에 안 걸렸지만 금융지주회사), business(사업형·중간 지주 5: 삼성물산·HD한국조선해양·두산·LS·한화, 이전 시드 목록). 합계 19
  - `sub_industry`는 KIND 후보 34개를 고쳐 확정해 노출하고(`sub_industry_source: krx_kind+review(#61)`), 후보가 없는 종목의 초안(에이피알 등)은 계속 숨긴다. 고친 것: 한화솔루션 방산 → 화학·태양광, 한화시스템 전자부품·PCB → 방산·ICT, 레인보우로보틱스 반도체 장비 → 로봇, 리노공업 → 반도체 테스트 소켓, LG이노텍 → 카메라모듈·기판, 삼성전기 → MLCC·패키지기판, 두산 → 전자소재(CCL), 포스코퓨처엠·에코프로비엠 → 2차전지 소재(양극재), SK이노베이션 → 정유·배터리
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

## 3. 섹터 속성 (`nodes.sectors`, `draft_fields`) — ⚠️

정성 판단이다. 이번 대조에서 바뀐 것은 없고 `wics_code`·`wics_name`만 추가했다.

| 속성 | 값 | 기준 |
|---|---|---|
| `cycle_type` | defensive / growth / cyclical | GICS 일반론. 필수소비재·헬스케어·유틸리티 = defensive, IT·커뮤니케이션 = growth, 나머지 = cyclical |
| `rate_sensitivity` | high / medium / low | high = 먼 미래 현금흐름 비중이 큰 성장주, 채권 대체재(유틸리티). low = 필수소비재·에너지 |
| `fx_sensitivity` | positive / negative / neutral | 원화 약세(USD/KRW 상승) 시 이익 방향. 수출 비중 큰 섹터 = positive, 원재료·연료 수입 의존 = negative, 혼재 = neutral |

**v0.8 (#61): 금리·환율 등급은 노출하지 않는다.** 시장 효과를 뺀 섹터 중앙값으로는 모든 섹터가 금리 low·환율 neutral에 가깝다(에너지 금리 medium, 유틸리티 high는 종목 1~5개). 초안(이론)은 데이터가 뒷받침하지 않고, 데이터 등급을 쓰면 관련 없는 종목이 섞여 희석된 값을 "둔감하다"는 사실처럼 보여 주게 된다. 그래서 `draft_fields`로 두고, 금리·환율 민감도는 종목 → 매크로 엣지(팀 합의 후)에서 다룬다.

**검증 계획 (v0.5).** 수경의 섹터별 corr_daily 집계가 오면 부호·크기로 이 라벨을 확인한다. 어긋나면 라벨을 고친다 (라벨이 회귀 값을 덮어쓰지 않는다). WICS 재분류로 섹터 구성이 바뀐 만큼(위 7종목) 라벨 재점검이 필요하다.

## 4. 매크로 지표 (`nodes.macros`)

수경 파이프라인은 **ECOS만** 수집하고 FRED·NBS·TrendForce 수집기는 없다. 시드 각 지표에 `pipeline_status`(collecting / not_planned), `pipeline_table`, `pipeline_key`, `pipeline_item_code`를 추가했다.

**v0.8 (#61): `direction`은 데이터와 초안이 같은 것만 노출한다.** 시장(일별 코스피 수익률, 월별 핵심 종목 동일가중 평균)과 지표 변화의 상관이고, Fisher 95% 신뢰구간이 0을 포함하지 않으면 `up_positive`/`up_negative`, 아니면 `mixed`다. 근거는 `direction_evidence`(source·method·as_of·corr·ci95·n).

| 지표 | 시장과 상관 | 95% 구간 | 표본 | 데이터 판정 | 초안 | 결과 |
|---|---|---|---|---|---|---|
| `KTB_3Y_KR` | −0.164 | −0.23 ~ −0.09 | 727일 | up_negative | up_negative | ✅ 노출 |
| `KTB_10Y_KR` | −0.132 | −0.20 ~ −0.06 | 727일 | up_negative | up_negative | ✅ 노출 |
| `USD_KRW` | −0.005 | −0.08 ~ +0.07 | 727일 | mixed | mixed | ✅ 노출 |
| `BRENT` | +0.131 | −0.05 ~ +0.30 | 120개월 | mixed | mixed | ✅ 노출 |
| `BASE_RATE_KR` | 변경 6건 중 같은 방향 3·반대 3 | – | 6 | mixed | up_negative | 초안 유지 |
| `CPI_KR` | +0.010 | −0.17 ~ +0.19 | 120개월 | mixed | up_negative | 초안 유지 |
| `DRAM_EXPORT_PRICE` | +0.163 | −0.02 ~ +0.33 | 120개월 | mixed | up_positive | 초안 유지 |

`KOSPI`는 시장 자체라 계산 대상이 아니고 초안(`up_positive`)으로 둔다.

**수집 중 8개 — ✅ (ID·항목코드는 파이프라인 값)**

| indicator_id | 테이블 | 키 / ECOS 항목코드 | 주기 | 비고 |
|---|---|---|---|---|
| BASE_RATE_KR | `macro_data` | 722Y001 / 0101000 | daily | v0.2는 `event`였으나 파이프라인이 일별 저장 |
| KTB_3Y_KR | `macro_data` | 817Y002 / 010200000 | daily | 민감도 요인 |
| KTB_10Y_KR | `macro_data` | 817Y002 / 010210000 | daily | |
| USD_KRW | `macro_data` | 731Y001 / 0000001 | daily | 민감도 요인 |
| CPI_KR | `macro_data` | 901Y009 / 0 | monthly | |
| BRENT | `macro_data` | 902Y003 / 010103 | monthly | v0.2 `OIL_BRENT`(FRED 일별)에서 변경. **ECOS 월평균** |
| DRAM_EXPORT_PRICE | `macro_data` | 402Y016 / 30911201AA/D | monthly | v0.4 `DRAM_PRICE`(TrendForce, 유료)를 **대체**. 한국은행 수출물가지수 품목별 D램 **달러기준**(원화기준은 환율이 섞여 제외), 2020=100. 수경 PR #34 (`macro_data_collector.py`) |
| KOSPI | `index_daily` | index_code `1001` | daily | v0.2 `KOSPI_INDEX`에서 변경. `macro_data`가 아니라 `index_daily`. 민감도 요인명도 `KOSPI` |

**수집 계획 없음 6개 — ⚠️ 비활성 보관 (수경 2026-11-10: "FRED 지표는 아직 수집 계획에 없음")**
`US_FFR`, `US_10Y_YIELD`, `USD_CNY`, `VIX`(FRED), `PPI_KR`(ECOS 코드 미확인), `CHINA_PMI_MFG`(NBS).
- 결정(유민, 중간안): **삭제하지 않고** 매크로와 거기 걸린 엣지에 `status: "inactive"`, `inactive_reason: "no_data_source"`를 단다. 삭제하면 아젠다 경로 설계가 사라지고, 그대로 두면 데이터 없는 근거 없는 주장이 주입되기 때문이다.
- 비활성은 `get_ontology_context` 주입과 Judge 경로 검증에서 뺀다. 데이터 수집이 생기면 `status`만 `active`로 바꾸면 된다 (기획서의 off → shadow → on 구조와 같은 방식).
- 로더(`ontology_seed.py`)의 `nodes()` · `edges()` · `company_context()`는 노출 가능한 것만 돌려준다. 검수용으로 초안까지 보려면 `include_draft=True`(비활성은 이때도 빠진다).
- **v0.5: `DRAM_PRICE`는 비활성 목록에서 빠졌다.** 수경이 무료 대체 지표(`DRAM_EXPORT_PRICE`)를 수집하기로 해서 ID를 바꾸고 활성화했다. 이 엣지(SEC_IT → `DRAM_EXPORT_PRICE`, IMPACTS `DRAM_EXPORT_PRICE → KOSPI`)가 다시 활성이다. TrendForce 현물·고정가가 아니라 **수출물가지수라 시차·성격이 다르다**는 점은 프롬프트 표현에서 "D램 수출물가"로 구분해야 한다.

**참고.** 파이프라인에는 시드에 없는 `WTI`, `DUBAI`, `EXPORTS_KR`, `IMPORTS_KR`, `IPI_KR`, 계산 지표 `TRADE_BALANCE_KR`도 이미 있다. 수출 비중이 큰 섹터 엣지의 후보지만, 근거 없이 넣지 않았다.

**스펙과 다른 점.** `category` 예시값(rate / fx / commodity / market)에 `inflation`, `sentiment` 두 개를 추가했다. 승인 필요. 파이프라인 `macro_data`에는 category 컬럼이 없으므로 category는 온톨로지 쪽 속성이다.

## 5. ISSUE 26개 (`nodes.issues`, `status: draft`, `reviewed: false`) — ⚠️

**선정 기준 (셋 다 충족).**
1. T1 종목 1개 이상에 영향을 주는 경로를 한 문장으로 설명할 수 있다
2. 하루짜리 뉴스가 아니라 지속되거나 반복되는 이슈다
3. Bull과 Bear 양쪽 논거로 쓸 수 있다

**값의 의미.** `polarity`는 연결된 종목·섹터 입장에서의 방향(positive → BENEFITS, negative → HURTS). `strength`는 매출·이익 영향 비중에 대한 정성 판단(high = 핵심 사업 직결, mid = 주요 사업 일부, low = 간접). `duration`은 persistent / cyclical / event_driven이고 `review_cycle_days`(180 / 90 / 30)는 재검토 주기 제안값이다.

**근거 청크 — 아직 연결 안 됨 (v1.2 필수 속성).** `evidence_chunk_ids`, `valid_from` / `valid_to`가 비어 있다. 수경 답변(2026-11-10)으로 연결 방법은 확정됐다.
- 벡터 저장소는 Supabase **pgvector**로 이전됐다 (v0.2 조사 시점 코드에는 Pinecone).
- 리포트 94종목 (2026-08-07 ~ 11-06, 활성 청크 17,272개) · 뉴스 98종목 (기사 6,822건, 청크 11,576개, 최근 2주 위주) · 공시는 적재 진행 중.
- `chunk_id`는 내용 기준이라 재적재해도 같다. 청킹 규칙이 바뀌어 사라진 청크는 삭제하지 않고 `is_active=false`로 남기므로 예전 id로 찾아도 깨지지 않는다. 뉴스 id는 원문 URL 기준이다.
- 따라서 `evidence_chunk_ids`에는 `chunk_id`를 저장하고, `valid_from`은 근거 청크 날짜, `valid_to`는 `review_cycle_days`로 정한다. DB 조회 권한이 필요해 이번 PR에서는 비워 두었다.

**확정 규칙 제안.** 근거 청크를 1개 이상 못 찾은 이슈는 시드에서 뺀다. 이 규칙을 통과해야 `status: draft` → `confirmed`. 뉴스가 최근 2주 위주라 오래된 `persistent` 이슈는 리포트 청크로 근거를 찾아야 할 수 있다.

## 6. 엣지

### BELONGS_TO (COMPANY → SECTOR, 100개) — ✅
종목 → 섹터 배정(2번, 파이프라인 값)에서 기계적으로 생성.

### BENEFITS / HURTS (ISSUE → COMPANY 또는 SECTOR, 98개) — ⚠️
ISSUE 정의에 포함된 대상 목록에서 생성. v0.2의 100개에서 **제외된 종목 대상 2개를 버렸다**. 섹터 단위 엣지는 해당 섹터 전체에 영향이 고른 경우에만 걸었고, 같은 이슈가 섹터와 종목 둘 다에 걸리면 종목 엣지를 우선한다. 추가된 KOSDAQ 10종목에는 엣지가 없다.

### EXPOSED_TO (COMPANY → ISSUE, 93개) — ⚠️
BENEFITS/HURTS 중 종목 대상 엣지를 뒤집고 `strength`를 숫자로 바꿨다 (high 0.9 / mid 0.6 / low 0.3). 독립적으로 판단한 값이 아니므로 `exposure_source`에 변환 규칙을 적어뒀다. 매출 비중 데이터가 생기면 교체한다.

### SENSITIVE_TO (SECTOR → MACRO, 28개: 활성 20 · 비활성 8) — ✅ weight 채움
- **weight는 수경 값 그대로다.** 추정·보정·반올림 변경 없음. 출처: 수경 PR #29 코멘트(2026-11-10)의 섹터 중앙값 표. 값은 PR #34(`sector_sensitivities`, `sector_monthly_correlations` 뷰)에 있고 **#34가 병합되기 전이라 코드 경로는 PR 기준**이다.
- **일별(KOSPI·USD_KRW·KTB_3Y_KR·KTB_10Y_KR):** `sector_sensitivities.corr_daily_median`, 일별 변화 최근 3년, `weight_as_of` 2026-11-06. 종목별 `corr_daily`(`sensitivities`)의 WICS 대분류 중앙값이다. 기획서 v1.2의 "일별 수익률 표준화 계수(상관 기반 민감도)"에 해당한다 (`beta`는 다른 값).
- **월별(CPI_KR·BRENT·DRAM_EXPORT_PRICE):** `sector_monthly_correlations.corr_monthly_median`, 월별 변화 최근 최대 120개월, **t월 주가 수익률 ↔ t+1월 지표 변화(1달 시차)**. 지표는 월평균이고 주가는 월말 종가라서 이렇게 짝을 지었다. `weight_as_of`는 CPI_KR 2026-10-01, BRENT·DRAM 2026-09-01. IT만 종목 수 18(LG씨엔에스 상장 24개월 미만 제외).
- 필드: `weight`, `weight_source`, `weight_window`, `weight_as_of`, `weight_n_tickers`, `weight_status: filled`, `weight_frequency`. 비활성 엣지는 모두 null. `build_seed.py`는 채워진 엣지에 이 필드가 하나라도 없거나 weight가 ±1을 넘으면 실패한다.
- **금리 엣지는 섹터당 하나만 둔다.** `KTB_3Y_KR`과 `KTB_10Y_KR`은 일별 변화 상관이 0.9라 둘 다 두면 같은 효과가 두 번 들어간다(수경 지적). 기획서 v1.2도 SENSITIVE_TO 예시에서 섹터당 금리 엣지 하나(`ktb_rate`)만 쓰고, 07의 "많이 쓸수록 점수 오르는 지표 삭제" 원칙과도 맞는다. 현재 섹터별 금리 엣지는 3년물(IT·경기소비재·금융)이거나 10년물(커뮤니케이션서비스·건강관리·유틸리티)이고 **한 섹터에 둘이 같이 있는 경우는 없다**. 무결성 검사가 이를 확인한다. 어느 쪽을 쓸지는 값 차이가 0.03 이하라 가설 근거로 정했다(NIM 민감 업종은 단기 3년물, 할인율 민감 업종은 장기 10년물). 10년물은 수경이 multi 회귀에 넣지 않았고 simple 회귀와 `corr_daily`만 있다.
- **expected_sign 부호 검증 (`sign_check`).** 가설을 회귀 값으로 덮어쓰지 않고 결과만 기록한다. `near_zero`는 |weight| < 0.02라 부호를 판단하지 않는다.

| 섹터 | 매크로 | 가설 | weight | 종목 수 | as_of | 부호 검증 |
|---|---|---|---|---|---|---|
| IT | `KTB_3Y_KR` | - | -0.111 | 19 | 2026-11-06 | match |
| IT | `USD_KRW` | + | -0.001 | 19 | 2026-11-06 | near_zero |
| IT | `DRAM_EXPORT_PRICE` | + | +0.121 | 18 | 2026-09-01 | match |
| 커뮤니케이션서비스 | `KTB_10Y_KR` | - | -0.075 | 7 | 2026-11-06 | match |
| 경기관련소비재 | `USD_KRW` | + | +0.001 | 7 | 2026-11-06 | near_zero |
| 경기관련소비재 | `KTB_3Y_KR` | - | -0.086 | 7 | 2026-11-06 | match |
| 경기관련소비재 | `CPI_KR` | - | +0.118 | 7 | 2026-10-01 | mismatch |
| 필수소비재 | `USD_KRW` | - | -0.004 | 2 | 2026-11-06 | near_zero · 종목 수 적음 |
| 건강관리 | `KTB_10Y_KR` | - | -0.081 | 7 | 2026-11-06 | match |
| 건강관리 | `USD_KRW` | + | -0.012 | 7 | 2026-11-06 | near_zero |
| 금융 | `KTB_3Y_KR` | + | -0.087 | 15 | 2026-11-06 | mismatch |
| 금융 | `KOSPI` | + | +0.398 | 15 | 2026-11-06 | match |
| 산업재 | `USD_KRW` | + | -0.002 | 31 | 2026-11-06 | near_zero |
| 산업재 | `BRENT` | - | +0.224 | 31 | 2026-09-01 | mismatch |
| 소재 | `BRENT` | ± | +0.110 | 5 | 2026-09-01 | — |
| 에너지 | `BRENT` | ± | +0.274 | 5 | 2026-09-01 | — |
| 에너지 | `USD_KRW` | - | -0.055 | 5 | 2026-11-06 | match |
| 유틸리티 | `BRENT` | - | +0.144 | 1 | 2026-09-01 | mismatch · 종목 수 적음 |
| 유틸리티 | `USD_KRW` | - | -0.032 | 1 | 2026-11-06 | match · 종목 수 적음 |
| 유틸리티 | `KTB_10Y_KR` | - | -0.155 | 1 | 2026-11-06 | match · 종목 수 적음 |

  - **v0.7: mismatch 4개·near_zero 5개는 모두 기각(`status: rejected`).** 수경이 섹터 소속 종목별로 같은 부호 비율·방향이 확실한 종목 수를 세고, 시장 효과(일별 코스피, 월별 핵심 98종목 평균 수익률)를 뺀 상관을 다시 냈다(PR #29 코멘트 2026-11-23).
    - 금융→`KTB_3Y_KR`: 은행만 봐도 6/6 음수라 업종이 섞여 뒤집힌 것은 아니다. 시장을 빼면 중앙값 은행 −0.007·증권 +0.010·보험 +0.047, 시장·환율을 통제한 30일 베타도 방향 확실 0개. NIM 효과는 은행 이자이익 데이터가 없어 확인 못 함.
    - 산업재→`BRENT`: 임시 기준(같은 부호 70%·방향 확실 과반·3종목 이상)은 통과했지만, 시장을 빼면 자본재 +0.001·운송 +0.100(유의하지 않음). 주식시장이 t+1월 유가를 앞서 움직인 결과다.
    - 경기소비재→`CPI_KR`(방향 확실 1/7), 유틸리티→`BRENT`(1종목), `USD_KRW` 5개(같은 부호 53~71%, 방향 확실 0~5개): 기준 미달.
    - 엣지마다 `rejection`(결정자·날짜·근거·수치)을 남겼다. 지우지 않는 이유는 같은 가설을 다시 넣지 않게 하려는 것이다.
  - **v0.7: 시장 효과를 빼지 않은 상관은 노출하지 않는다.** 위 검증에서 상관의 상당 부분이 시장 전체 움직임으로 설명됐다(코스피 일별 수익률과 국고채 3년 변화 상관 −0.18, 시장과 t+1월 유가 변화 상관 +0.33). 지금 weight는 모두 시장 효과를 빼지 않은 섹터 중앙값이라, `KOSPI`(시장 자체) 엣지를 뺀 10개를 `needs_review`(`review_reason: market_unadjusted`)로 돌렸다. 시장 효과를 뺀 값이 오면 `market_adjusted: true`로 다시 판정한다. 기준에 "시장 효과를 뺀 뒤에도 같은 부호가 남는가"를 넣자는 수경 제안을 따른 것이다.
  - **v0.7 (#56 반영): 보류 10개도 모두 기각.** 수경이 종목 수익률과 요인 변화 **양쪽에서** 시장 효과를 뺀 편상관을 냈다(일별 최근 3년 ~2026-11-06, 월별 최대 120개월, 95% 신뢰구간은 Fisher 변환). 같은 기준(같은 부호 70% 이상, 방향 확실 과반, 종목 3개 이상)으로 10개 모두 미달이다. 방향은 가설과 맞는 엣지가 많지만(건강관리→`KTB_10Y_KR` 7/7, 에너지→`USD_KRW` 5/5) 크기가 −0.01~−0.06으로 작고, IT→`KTB_3Y_KR`은 0.000이 됐다. 근거는 `build_seed.py`의 `REJECTED_56`과 각 엣지의 `rejection` 필드. 섹터 중앙값은 관련 없는 종목이 섞여 작아지지만 핵심 종목은 시장 효과를 빼도 뚜렷해서(삼성전자·SK하이닉스→`DRAM_EXPORT_PRICE` +0.21, S-Oil→`BRENT` +0.30 등), 종목 → 매크로 엣지 도입을 팀에 제안한다(후속, 합의 후 v0.8).
  - **v0.7: 섹터 → `KOSPI` 엣지를 10개 섹터 모두에 둔다.** 값은 수경 표의 `corr_daily` 중앙값(as_of 2026-11-06)이고, KOSPI는 시장 자체라 시장 효과를 뺄 대상이 아니다. 기각 기준과 같이 종목 3개 미만인 필수소비재(2)·유틸리티(1)는 `needs_review`(`low_n`). 금융 ← KOSPI는 기존 가설("증권 브로커리지")을 그대로 뒀다. 토론에서는 "이 섹터가 시장과 같이 움직이는 정도"로만 쓴다.
  - **종목 수 3개 미만 섹터**(필수소비재 2, 유틸리티 1)는 `weight_low_n: true`.
  - **섹터 중앙값은 관련 없는 종목이 섞여 희석된다.** 예: D램은 IT 섹터 0.121이지만 삼성전자 0.27, SK하이닉스 0.26이라 핵심 경로는 **종목 단위 SENSITIVE_TO**가 더 적합하다 (기획서 v1.2 엣지 정의는 `SECTOR / COMPANY → MACRO`). 이번 PR에는 섹터 값만 넣었다. 종목 단위 엣지는 수경에게 종목별 값(출처·as_of 포함)을 받은 뒤 후속으로 추가한다.
- **BASE_RATE_KR 합침(v0.4).** 기준금리는 일별로 저장되지만 정책 결정일에만 바뀌는 계단식 값이라 일별 수익률과의 상관이 의미 없다. 같은 방향의 금리 가설을 `KTB_3Y_KR`로 옮겼다. 합친 엣지에는 `merged_from: ["BASE_RATE_KR"]`, `meta.merged_sensitive_edges`에 3건(renamed 2, dedup 1)과 원래 `expected_sign`을 남겼다. `BASE_RATE_KR` 노드와 IMPACTS 엣지는 그대로다.
- **비활성 8개** (수집 계획 없는 매크로 6개): IT→`US_10Y_YIELD`·`VIX`, 경기소비재→`CHINA_PMI_MFG`, 필수소비재→`PPI_KR`, 금융→`VIX`, 산업재→`CHINA_PMI_MFG`, 소재→`CHINA_PMI_MFG`·`USD_CNY`. `weight_status: null`.
- 삭제: `SEC_REAL_ESTATE → KTB_10Y_KR` (섹터 삭제, 2번 참고).

### SENSITIVE_TO (COMPANY → MACRO, 10개) — v0.9
섹터 엣지는 시장 효과를 빼면 전부 기준 미달이었지만(위), 핵심 종목은 관계가 남는다. 수경이 99종목 × 6지표의 시장 효과 뺀 편상관을 냈고(#56 2026-11-23, #62 `sensitivities --level ticker`), 아래 기준을 **모두** 만족하는 것만 넣었다.

1. 시장 효과 뺀 값의 95% 신뢰구간이 0을 포함하지 않음
2. |값| ≥ 0.10 (일별 표본이 약 730일이라 작은 값도 확실로 나옴)
3. 경제적 가설이 있고 부호가 같음 — 다중 비교 대비. 가설 없이 데이터에서만 나온 관계(레인보우로보틱스 → D램 −0.37, 크래프톤 → CPI, 은행·보험 → 유가)와 가설과 반대인 관계(에이피알 → 원/달러 −0.104)는 넣지 않음
4. 가설 엣지끼리 BH 보정한 q < 0.05 (수경 제안: 보정은 실제로 본 개수에 맞춘다). 지표별 99종목 전체 보정 q(`weight_q_value_all`)는 참고값으로 남김 — 이 기준이면 대한항공·한국전력 4개만 0.05 미만

| 종목 | 지표 | 시장 효과 뺀 값 | 95% 구간 | q(가설 10개) | q(99종목) | 가설 |
|---|---|---|---|---|---|---|
| 대한항공 | `KTB_3Y_KR` / `KTB_10Y_KR` | −0.179 / −0.156 | −0.25~−0.11 / −0.23~−0.08 | 0.00001 / 0.0001 | 0.0001 / 0.002 | 부채·리스 부담 |
| 한국전력 | `KTB_3Y_KR` / `KTB_10Y_KR` | −0.122 / −0.119 | −0.19~−0.05 | 0.002 / 0.003 | 0.032 / 0.033 | 부채가 큰 규제 유틸리티 |
| 한진칼 | `KTB_3Y_KR` | −0.101 | −0.17~−0.03 | 0.009 | 0.109 | 대한항공 지주 |
| 카카오 | `KTB_10Y_KR` | −0.106 | −0.18~−0.03 | 0.007 | 0.084 | 성장주 장기 할인율 |
| S-Oil / SK이노베이션 | `BRENT` (월) | +0.303 / +0.225 | +0.13~+0.46 / +0.05~+0.39 | 0.002 / 0.017 | 0.075 / 0.269 | 정유 재고·마진 |
| 삼성전자 / SK하이닉스 | `DRAM_EXPORT_PRICE` (월) | +0.218 / +0.214 | +0.04~+0.38 | 0.019 / 0.019 | 0.404 / 0.404 | 메모리 가격 |

**운영 규칙 (수경 #64 리뷰, ADR 0003 개정에서 확정).**
- 이번 10개는 방향 확실 68개를 **본 뒤에** 가설을 붙였다(`hypothesis_preregistered: false`). 그래서 "가설 10개 안에서 보정"한 q값은 실제보다 조금 낙관적이다. 목록과 가설을 2026-11-23에 고정하고(`hypothesis_fixed_on`), **다음 월간 계산부터 같은 목록을 새 값으로 다시 판정**한다. 그때부터 4번 기준이 뜻대로 작동한다
- 새 엣지는 가설을 먼저 적고 값을 본다. 가설 없이 데이터에서 찾은 관계는 지표별 99종목 q값으로 거른다
- 다시 판정해서 기준에서 한 번 떨어지면 `needs_review`(노출 멈춤), 두 달 연속이면 `rejected`. 99종목 q값이 0.05를 넘는 6개와 크기 기준에 가까운 한진칼(−0.101)·카카오(−0.106)가 먼저 떨어질 수 있다
- 근거 칩은 `chip_text`를 쓴다. 월별 엣지는 "t월 주가 ↔ t+1월 지표 변화", 즉 주가가 다음 달 지표 변화를 먼저 반영하는 관계라 원인처럼 쓰지 않는다(예: "시장 효과를 빼도 주가가 다음 달 D램 수출물가지수 변화와 같은 방향으로 움직이는 경향 (월별)"). `rationale`은 "왜 그럴 수 있는지"로만 쓴다

`weight`는 시장 효과를 뺀 값(`market_adjusted: true`)이라 섹터 엣지(원래 상관)와 크기를 바로 비교하지 않는다. 로더 `company_context`는 `company_sensitivities`로 따로 돌려준다. 보류: S-Oil·GS → 국고채(+0.13, 확실)는 금리와 직접 이어지는 경로를 못 찾아 넣지 않았다. 매달 값은 수경 월간 계산(`ontology_sensitivity_inputs`, #56)이 생기면 그걸 읽게 바꾼다.

### IMPACTS (MACRO → MACRO, 15개: 노출 1 · 초안 5 · 비활성 9) — ⚠️
**v0.8 (#61): `CPI_KR → BASE_RATE_KR`(같은 방향)만 노출한다.** 월별 변화 1달 시차 상관 +0.166(95% +0.04 ~ +0.29, 240개월)로 초안과 같다. 근거는 `evidence` 필드. 나머지는 방향이 불분명해서 초안이다: 기준금리 변경 −1 → +5거래일 사건 분석에서 국고채 3년·10년·환율과 같은 방향 52~57%(기준 65%), `USD_KRW → CPI_KR` 상관 −0.016, `DRAM_EXPORT_PRICE → KOSPI` 상관 +0.158(구간이 0 포함). 기준금리는 시장이 미리 반영하는 경우가 많아 짧은 사건 창으로는 방향이 잘 안 보인다.

끝점 중 하나라도 수집 계획 없는 매크로면 `status: inactive`(`inactive_macros`에 해당 지표). 활성 6개는 `BASE_RATE_KR→KTB_3Y_KR`·`BASE_RATE_KR→KTB_10Y_KR`·`BASE_RATE_KR→USD_KRW`·`USD_KRW→CPI_KR`·`CPI_KR→BASE_RATE_KR`·`DRAM_EXPORT_PRICE→KOSPI`.

표준 거시 전달 경로(정책금리 → 시장금리, 금리차 → 환율, 유가 → PPI → CPI, 위험회피 → 원화 약세 등). 스펙상 IMPACTS는 방향만 명시하므로 `relation`(same / opposite)만 두고 weight는 없다. ID만 파이프라인 이름으로 바꿨다(`BRENT`, `KOSPI`).

### COMPETES_WITH
만들지 않았다. COMPETITOR 노드를 COMPANY로 합칠지(유민 제안)가 미결이다.

## 7. 재현 방법

```bash
python scripts/extract_t1.py core_companies_2026-11-09.csv   # CSV 형식 검증
python scripts/build_seed.py core_companies_2026-11-09.csv .  # 시드 생성 + 무결성 검사
```

`build_seed.py`는 정의 데이터(이슈, 엣지 쌍)를 코드 안에 담고 있고 표준 라이브러리만 쓴다. 실행하면 `ontology_seed.json` 하나를 다시 쓰며, 같은 입력이면 바이트 단위로 같다(`tests/test_ontology_seed.py`가 확인). 무결성 검사: 종목 100개·중복 없음, 엣지 양 끝 노드 존재, 이슈·지표 ID 중복 없음, 소속 종목 없는 섹터 없음, 출처 없는 weight 금지, 비활성 매크로에 걸린 엣지는 반드시 비활성(그 반대도), 활성 엣지의 `weight_status`는 값이 있고 비활성은 없음, SENSITIVE_TO 쌍 중복 없음, `W_N`(섹터 종목 수) = core 소속 종목 수 − `0126Z0`, 노출 가능한 엣지는 `source`·`method`·`as_of` 필수.

```bash
python -m pytest ontology/seed/tests -q   # 재생성 일치 · 노출 규칙 · 계약 필드
```

## 8. 팀원 확인 요청

| 누구 | 무엇 | 상태 |
|---|---|---|
| 수경 | 섹터별 weight 집계, `KTB_10Y_KR`·`CPI_KR`·`BRENT` 요인, DRAM 대체 지표 | ✅ 2026-11-10 PR #29 코멘트로 회신 (v0.5 반영) |
| 수경 | IT→`DRAM_EXPORT_PRICE` 등 핵심 경로의 **종목 단위** 월별 상관값(삼성전자 0.27·SK하이닉스 0.26 등)과 출처·as_of | 요청 필요 |
| 유민 | 수집 계획 없는 지표 6개 | ✅ 결정: 삭제 않고 `inactive` 보관 (v0.4) |
| 유민 | 부호 불일치 4개(경기소비재→CPI, 금융→KTB_3Y, 산업재→BRENT, 유틸리티→BRENT)와 `USD_KRW` near_zero 5개 엣지 유지 여부 | ✅ 결정: 9개 모두 `rejected` (v0.7, 수경 검증 근거) |
| 수경 | `market_unadjusted` 10개 엣지의 시장 효과를 뺀 섹터 중앙값(일별은 코스피, 월별은 핵심 종목 평균 기준)과 종목 부호 일치·방향 확실 수 | ✅ 이슈 #56 회신 2026-11-23 |
| 유민 | 보류 10개 판정 | ✅ 결정: 10개 모두 `rejected` (#56, 같은 기준 미달) |
| 전원 | 종목 → 매크로 SENSITIVE_TO 도입(삼성전자·SK하이닉스→D램, S-Oil·SK이노베이션→유가, 카카오·NAVER→국고채 10년 등. 값은 `sensitivities`·`monthly_correlations`) · 노출 기준을 ADR 0003 개정에 넣기 | 제안 (#56) |
| 수경 | 시장 효과 뺀 값 매달 자동 계산 | 진행 중 (#62 `monthly`, 저장 테이블 형식은 #56에서 논의) |
| 유민 | 섹터 금리·환율 등급, 매크로·IMPACTS 방향, 지주사·세부 업종 (#61) | ✅ 결정 (v0.8) |
| 유민 | **다음 작업:** ISSUE 26개·BENEFITS/HURTS 98·EXPOSED_TO 93 검수와 근거 청크 연결(`get_chunks_by_ids`·`search_documents`, #53 병합 후). 검수 끝난 것부터 `reviewed: true`로 노출 | 다음 |
| 유민 | KOSDAQ 신규 10종목의 이슈 엣지 라벨링, `is_holding`·`sub_industry` 검토 | 후속 |
| 태은 | 노출 규칙·엣지 공통 필드·JSON 단일화 (PR #29 리뷰 1·2·3·6) | ✅ v0.6 반영 |
| 태은 | ADR 0003 월별 예외 문서화 (리뷰 4, 태은 작성 제안) · DB 적재기 (`ontology_nodes`·`ontology_edges`) | 후속 |
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
| v0.5 | 2026-11-10 | 수경 섹터 중앙값으로 SENSITIVE_TO weight 채움(활성 20개, 출처·기간·as_of·종목 수·`weight_frequency`), `DRAM_PRICE`→`DRAM_EXPORT_PRICE`(ECOS 402Y016) 교체·활성화, 금리 엣지 섹터당 1개 검사 추가, `sign_check`·`weight_low_n` 필드, `weight_status`를 filled / not_available로 정리 (SENSITIVE_TO 활성 20·비활성 8, IMPACTS 활성 6·비활성 9) |
| v0.6 | 2026-11-22 | 태은 리뷰 반영. 모든 노드·엣지에 `status`·`reviewed`, 노출 = active + reviewed. 엣지 공통 필드(`relation`·`src`·`dst`·`source`·`method`·`as_of`·`valid_from`·`valid_to`·`evidence_ids`), IMPACTS 방향은 `direction`. Claude 초안 엣지·이슈는 `draft`, SENSITIVE_TO mismatch 4·near_zero 5는 `needs_review`(노출 11개). 노드 초안 속성은 `draft_fields`. 섹터 이름 WICS, `valid_until`→`valid_to`, `weight_low_n` bool, `W_N` 검증. 원본 JSON 하나(`ontology_seed.json`)·손으로 쓴 로더·pytest |
| v0.9 | 2026-11-23 | 종목 → 매크로 SENSITIVE_TO 10개(#56). 기준: 확실 + |값| ≥ 0.10 + 가설 부호 일치 + 가설 엣지끼리 BH q < 0.05. `weight_p_value`·`weight_q_value_hypothesis`·`weight_q_value_all`. 로더 `company_sensitivities`. 노출 SENSITIVE_TO 8 → 18 |
| v0.8 | 2026-11-23 | 수경 #61(PR #62 계산) 반영. MACRO `direction` 4개(`KTB_3Y_KR`·`KTB_10Y_KR`·`USD_KRW`·`BRENT`)에 `direction_evidence`를 붙여 노출, IMPACTS `CPI_KR → BASE_RATE_KR` 노출(`evidence`). `is_holding` 확정(19개, `holding_type`·`holding_source`), `sub_industry` 34개 확정. 섹터 금리·환율 등급은 초안 유지 |
| v0.7 | 2026-11-23 | 수경 검증(PR #29 코멘트) 반영. mismatch 4·near_zero 5 SENSITIVE_TO를 `rejected`(근거 `rejection` 필드), 시장 효과를 빼지 않은 KOSPI 외 10개를 `needs_review`(`market_unadjusted`), `market_adjusted` 필드 추가. 섹터 → KOSPI 엣지 9개 추가(종목 3개 미만 2개는 `low_n` 보류). 노출 SENSITIVE_TO 11 → 8(전부 KOSPI). 로더 `include_draft`도 `rejected`는 보여 주지 않음. 이어서 #56(시장 효과 양쪽 제거 편상관) 반영: 보류 10개도 `rejected`(`REJECTED_56`), 기각 19개·`needs_review` 2개(KOSPI `low_n`) |
