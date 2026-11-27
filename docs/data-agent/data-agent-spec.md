# 데이터 에이전트(Agent A+B) 기획서

| 항목 | 값 |
| --- | --- |
| 버전 | **v2.0** (2026-11-23) |
| 상태 | 검토 중 |
| 담당 | 수경 |
| 기능 ID | 없음 (다른 에이전트가 쓰는 공용 데이터 함수) |
| 계약 | [`docs/api/openapi.yaml`](../api/openapi.yaml) `1.0.0-draft.5` |
| 관련 결정 | ADR 0002(민감도 요인), 0003(온톨로지 엣지, 0011 제안으로 대체 예정), 0004(매크로 지표), 0005(pgvector), 0006(DataTier), 0010(컨센서스 180일) |
| 구현 계획 | #73(함수 계약 추가), #84(intent별 묶음), #55(위반 항목) |
| 코드 | `data-pipeline/crawling/`(수집·적재), `data-pipeline/processing/`(조회 함수·검색), `supabase/migrations/` |

## 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1 | 2026-10 | Notion 초안: 역할, 티어, 함수 목록 |
| v2 초안 | 2026-11-08 | 다른 에이전트 확정 사항, 금융 RAG 조사, 파싱·청킹·검색 설계, 계약서 정렬 |
| **v2.0** | 2026-11-23 | 저장소로 이관, 11/08 이후 구현 결과 반영 |

### v2 초안(11/08) → v2.0 무엇이 바뀌었나

| 항목 | v2 초안 | v2.0 | 근거 |
| --- | --- | --- | --- |
| 문서 청크·검색 | 설계만 | 리포트·뉴스·공시 청크 약 3.6만 개 적재, 하이브리드 검색이 기본 | 골든셋 평가(8절) |
| 신규 함수 | 미구현 | 6개 중 5개 구현(`ensure_company_data`만 Post-MVP), `get_chunks_by_ids` 추가, `suggest_alternatives` 리뷰 중 | #35, #53, #85 |
| 함수 호출 방식 | 도구 레지스트리를 거침 | 그대로 **도구 레지스트리를 거침(MVP)**. 함수의 `error`가 레지스트리의 `ToolResult.error`로 올라감 | 오케스트레이터 기획서 v2.2 |
| 목표주가 컨센서스 | 180일 제한은 제안 | 채택 | ADR 0010 |
| 데이터 상태 | 건수 3개 | 소스 11개의 건수·최신일(`sources`), 실패는 `null` + `error` | #53, #75 |
| 커버 판정 | 티어 기준 | 우선주가 아니고 적재된 종목 데이터(`macro` 제외)가 1개 이상 | 오케스트레이터 기획서 v2.2 |
| 온톨로지 입력값 | 민감도 값만 | 시장 효과를 뺀 민감도 계산·저장, 세부 업종·지주사·방향 근거·이슈 근거 후보 | #61, #62, #67, ADR 0011 |
| 정기 적재 | 없음 | GitHub Actions 워크플로(평일 적재, 매달 재계산), 머지 전 | #58 |
| 코드 위치 | 개인 레포 | 팀 레포 main | – |

## 1. 역할과 범위

| 에이전트 | 하는 일 |
| --- | --- |
| **Agent A** (기업 컨텍스트 해석) | 회사 이름·종목코드를 정확한 종목으로 특정("삼성전자" → `005930`)하고, 종목마다 데이터가 얼마나 있는지 알려 줌 |
| **Agent B** (데이터 인프라) | 데이터를 모으고, 가공하고, Supabase에 저장하고, 조회 함수로 내어 줌 |

```text
[A] 종목 특정 → 데이터 수준 확인 → [B] 수집 → 정규화 → 파싱·청킹 → 저장(Supabase) → 조회 함수
```

- 다른 에이전트는 조회 함수를 **도구 레지스트리(`invoke`)로** 부릅니다. 함수가 조회 실패를 `error`로 표시하면 레지스트리가 그대로 실패로 올립니다. 그래서 "실패를 없음으로 보이지 않기"(3-1절)가 특히 중요합니다.
- 모든 조회 함수는 Supabase(Postgres + pgvector)에서 읽습니다. 예전 SQLite·Pinecone 경로는 없앴습니다.

**데이터 에이전트가 하지 않는 일**

| 하지 않는 일 | 누가 함 | 데이터 에이전트는 |
| --- | --- | --- |
| LLM이 SQL을 직접 쓰기 | 정해진 경로만 실행(오케스트레이터) | 숫자를 결정적 함수(`get_metric` 등)로 제공 |
| 질문 거절 판단 | 관문1(오케스트레이터), precheck(토론) | 판단 재료(`data_status`, `data_tier`) 제공 |
| 답변 검증, 근거 재검색 | 각 에이전트의 검증 단계 | 값이 없으면 추측하지 않고 `null`과 사유 반환 |
| 온톨로지 노출 판정 | 온톨로지(유민) | 판정 재료(시장 효과 뺀 민감도, 후보) 계산 |

## 2. 종목 티어와 커버

### 2-1. 티어

| 티어 | 대상 | 데이터 | 지금 |
| --- | --- | --- | --- |
| **T0** | 전 종목 | 구조화 데이터만(시세·재무·업종) | 2,767종목. 종목 정보·업종만 있고 **시세·재무는 아직 없음**(DB 용량 결정 뒤 적재) |
| **T1** | 시가총액 상위 100개(`is_core`) | T0 + 리포트·뉴스·공시 본문 + 목표주가 + 수급·지분공시 | 100종목, 모두 적재 |
| **T2** | 처음 물어본 T0 종목 | 요청 시점에 T1 수준으로 수집 | 없음(Post-MVP) |

- `resolve_company`가 종목을 특정할 때 `tier`, `is_preferred`(우선주), `data_status`를 함께 알려 줍니다.
- MVP에서 T1은 100개로 고정합니다. 승격·강등과 T2 수집(`ensure_company_data`)은 Post-MVP입니다.

### 2-2. 커버 판정 (오케스트레이터 기획서 v2.2에서 확정)

| 상황 | 결과 |
| --- | --- |
| 우선주 | 미커버(`uncovered_company`) |
| 종목 데이터가 하나도 없음(지금 T0) | 미커버(`uncovered_company`) + 대안 종목 3개 |
| 커버 종목인데 그 화면에 필요한 데이터만 없음 | `no_data` + 대안 종목 3개 |
| `data_status` 조회 실패(`None` 또는 `error`) | 503 `upstream_unavailable`(데이터 없음과 구분) |

- **주의:** "종목 데이터가 하나도 없음"을 셀 때 `macro`는 빼야 합니다. `macro` 건수는 종목과 상관없는 지표 수라 T0에도 늘 13으로 나옵니다. 오케스트레이터 기획서 v2.2에 반영됐습니다.
- 티어는 거절 기준이 아니라 "얼마나 많이 보여 줄지"에만 씁니다.
- 대안 종목은 `suggest_alternatives(ticker, n=3)`로 데이터 쪽이 만듭니다(3-3절).

## 3. 조회 함수

### 3-1. 공통 규칙

1. **계약서를 따릅니다.** 계약서에 있는 필드는 이름과 뜻을 바꾸지 않고, 필요한 정보는 필드를 더해서 넣습니다. 함수를 바꾸면 계약서도 같은 PR에서 고칩니다.
2. **`as_of`로 시점을 맞춥니다.** `"YYYY-MM-DD"`, 기본값은 오늘(한국 시간). 넘기면 그날까지 공개된 데이터만 돌려줍니다.
   - 재무제표는 공시 접수일, 목표주가는 발표일, 리포트·뉴스·공시는 게시일, 시세는 거래일, 월별 지표는 그 달 기준입니다.
3. **값마다 기준일을 붙입니다.** 날짜는 한국 날짜(`YYYY-MM-DD`)입니다.
4. **값이 없으면 `null`과 사유를 줍니다.** 0이나 추측한 값으로 채우지 않습니다. 예: 금융 섹터 부채비율 → `reason: "not_applicable_financials"`
5. **조회 실패와 데이터 없음을 구분합니다.** 실패하면 예외 대신 `error`를 붙이고, 모르는 값은 0이 아니라 `null`로 둡니다.

### 3-2. 함수 목록

| 함수 | 하는 일 | 상태 |
| --- | --- | --- |
| `resolve_company(company_input)` | 종목 특정. 확정이면 종목코드·이름·업종·시총·티어·우선주·`data_status`, 애매하면 후보 목록 | ✅ |
| `search_companies(query, limit=10)` | 종목 후보 검색(완전일치 → 별칭 → 접두어 → 초성, 같으면 시총순) | ✅ |
| `extract_company_mentions(text)` | 문장 속 종목 찾기 | ✅ 조회 실패를 빈 목록과 구분하는 일은 #88 리뷰 중 |
| `search_documents(query, ticker, …, as_of, mode)` | 리포트·뉴스·공시 조각 검색(기본 하이브리드). 결과에 `chunk_id`, `doc_id`, 제목, 출처, 증권사, `broker_key`, 날짜, 본문. `keyword_query`를 주면 키워드 검색에만 씀(#106) | ✅ 종목 필터 GIN 색인(#111)·`chunk_type` 인자(#112)는 리뷰 중 |
| `get_chunks_by_ids(chunk_ids)` | 청크 ID로 본문 꺼내기(입력 순서대로, 없는 ID는 `missing`) | ✅ |
| `get_report_metadata`, `get_report_chunks` | 리포트 목록, 리포트 조각 전체 | ✅ |
| `get_target_price_data(ticker, …, as_of, revision_window_days)` | 증권사 목표가·의견 이력과 컨센서스(최근 180일, 증권사별 최신 1건, `broker_key`로 묶음), 개정 수 `revisions`(기본 90일) | ✅ #75, #105 |
| `get_price_data(ticker, …, as_of)` | 수정주가 시세 | ✅ |
| `get_macro_data(indicators, …, as_of)` | 매크로 지표 이력 | ✅ |
| `get_disclosure_data(ticker, …, as_of)` | 공시 목록(분류별), 첫 조각 요약, 수집 시작일(`coverage_from`) | ✅ |
| `get_financials(ticker, period_type, …, as_of)` | 분기·연간 재무(공시 접수일 기준, 연결/별도 표시) | ✅ |
| `get_market_snapshot(sector, top_n, sort_by, as_of)` | 조건에 맞는 종목 목록(WICS 업종) | ✅ 지금은 T1 안에서만 |
| `get_derived_snapshot(ticker, as_of)` | 계산 근거 4묶음: 밸류에이션 위치, 주가 흐름(수익률·변동성·52주 위치), 실적 추세, 수급 | ✅ 한 묶음 실패 시 전부 비는 문제는 #88 리뷰 중, 표본 부족 시 값이 나가는 문제 남음 |
| `get_metric(ticker, metric_id, as_of)` | 지표 하나를 정해진 정의로 계산(22개: 시세·밸류에이션 10, 재무 4, 수급 5, 지분공시 3). 표시용 `display` 포함. PER·EPS가 비면 직전 사업연도 적자인지 확인(`loss_making`) | ✅ #113 |
| `get_metrics(ticker, metric_ids, as_of)` | 여러 지표를 DB 연결 하나로 계산(지표마다 연결을 열면 약 0.35초씩 듦) | ✅ #108 |
| `get_index_data(indexes, as_of, days)` | 코스피·코스닥(·코스피200) 일별 종가 | ✅ #109 |
| `get_sensitivities(ticker, as_of)` | 종목의 시장 효과를 뺀 매크로 민감도(일별 3, 월별 3) | ✅ #109 |
| `get_available_data_status(ticker, as_of)` | 데이터 보유 상태. 소스 11개(리포트·뉴스·공시·시세·매크로·목표가·재무·수급·지분공시·민감도·계산 근거)의 건수와 최신일, `simulation_ready` | ✅ `as_of`(기준일 이전 파라미터로 `simulation_ready` 판정)는 #103 리뷰 중 |
| `get_agent_context(ticker, agent_type, query, intent, data_status, as_of)` | 에이전트별 데이터 묶음. `data_tier`·`as_of` 항상 포함 | 🟡 intent별 묶음(4절): 문서 검색 #106, 지표 #108, 블록·넓혀 찾기 #110 머지. 계산 근거 블록은 #88 뒤 |
| `suggest_alternatives(ticker, n=3)` | 대안 종목: 커버 종목 중 같은 중분류 → 대분류 → 전체, 시총순 | 🟡 #85 리뷰 중 |
| `ensure_company_data(ticker, user_id)` | T2 수집 예약 | Post-MVP |

**함수별로 알아 둘 것**

| 함수 | 내용 |
| --- | --- |
| `get_target_price_data` | 컨센서스는 증권사마다 가장 최근 의견 1건 중 **최근 180일 안**의 것만 씁니다. 더 오래된 증권사는 뺍니다. 액면분할은 환산합니다. 트렌드 리포트·토론·시뮬레이션은 이 값을 그대로 써서 화면마다 같은 값이 나옵니다. |
| `search_documents`·`get_target_price_data` (`broker_key`) | KIS 목표가("키움", "NH투자")와 리포트("키움증권", "iM증권")의 증권사 표기가 달라 그대로는 2곳만 같습니다. `broker_key`로 맞추면 삼성전자 기준 리포트 증권사 12곳 중 11곳이 이어집니다. |
| `get_derived_snapshot` (변동성) | 일별 로그수익률 표준편차 × √252. 비교 기준(`volatility_1m_market_threshold`)은 그날 시세가 있는 종목(지금 T1 100개)의 상위 20% 값이라 늘 약 20종목이 기준을 넘습니다. 화면에는 "최근 1개월 변동성 상위 20%(핵심 100종목 기준)"처럼 기준을 보이고, 시뮬레이션 변동성(GARCH)과 이름을 구분합니다. |
| `get_available_data_status` | 건수 단위가 소스마다 다릅니다. `macro`는 종목과 상관없는 지표 수(13), `sensitivity`는 요인 수, `derived`는 계산 가능하면 1입니다. 실패하면 `error="data_status_unavailable"`, 건수는 `null`, `sources`는 빈 객체입니다. |
| `get_agent_context` | `data_status`를 넘기면 상태를 다시 조회하지 않습니다(종목당 0.3–1초 절약). 트렌드 리포트는 리포트·뉴스 후보를 각 15개 받습니다. 매크로 문서는 없어서 검색하지 않습니다. |

## 4. intent와 data_tier

### 4-1. intent (토론 아젠다)

`intent` 값은 토론 아젠다 ID와 같습니다. precheck는 아젠다마다 "이 데이터 중 하나는 있어야 함"을 보고 토론을 할지 정합니다(`intent_data_sources.json`).

| intent | 아젠다 | precheck가 보는 데이터(하나라도 있으면 통과) | 묶음에 넣을 재료 (설계 중) |
| --- | --- | --- | --- |
| `valuation` | 실적·밸류에이션 | 재무, 시세, 목표가, 리포트 | PER·PBR·EPS·BPS·ROE·영업이익률·종가·시총, 밸류에이션 위치, 목표가·컨센서스, 최근 분기 재무, 주가 흐름, 리포트 |
| `macro` | 산업·매크로 | 민감도, 뉴스, 리포트 | 관련 매크로 지표, 코스피·코스닥, 이 종목의 민감도(시장 효과 뺀 값 포함), 리포트·뉴스 |
| `risk` | 리스크 | 수급, 지분공시, 공시, 뉴스, 리포트 | 부채비율·공매도·지분공시·외국인 순매수, 변동성, 최근 공시, 리포트·뉴스·공시 |
| `growth` | 성장 동력 | 재무, 계산 근거, 리포트, 뉴스 | 매출 성장률·영업이익률·ROE, 분기 실적 추세, 최근 분기 재무, 리포트·뉴스 |
| `shareholder_return` | 주주환원 | 공시, 시세, 리포트 | 배당수익률·DPS·EPS·종가, 주주환원 공시, 리포트·공시 |
| `flow` | 수급 | 수급 | 기관·외국인·개인 순매수, 공매도 거래·잔고, 뉴스 |

- **반환 모양(키 이름, 블록, 개수 상한)은 4-2절입니다.** 토론(유민)과는 #84에서 합의했고, 계약서 반영(Q5)은 오케스트레이터(태은)와 확인 중입니다. 원칙은 네 가지입니다.
  - 숫자는 `get_metric` 결과 그대로
  - 문서는 토론 근거(`Evidence`)로 바로 옮길 수 있는 모양
  - precheck가 "있다"고 판정한 데이터는 묶음에 꼭 포함
  - 한 블록이 실패해도 나머지는 줌
- 지수 조회(`get_index_data`)·민감도 조회(`get_sensitivities`)는 만들었고(#109), 과거 시점 기준 `data_tier`는 아직 없습니다.
- 시뮬레이션은 `intent` 없이 부르고, 묶음에 지수(`index_daily`)와 파라미터 기준일(`sim_params_as_of`)을 더할 예정입니다.

### 4-2. intent별 반환 모양 (토론 `agent_type="debate"`)

설계 논의는 이슈 #84에서 했습니다. 토론 쪽 질문(Q1–Q4)은 유민 답(11/24)으로 정했고, 계약서 반영(Q5)만 남았습니다.

**정해진 것**

| 항목 | 내용 | 근거 |
| --- | --- | --- |
| 부르는 방식 | 토론이 아젠다마다 1번씩, 아젠다끼리 병렬로 부름 | 토론 기획서 v3.0, #76 |
| 검색어 | 키워드 검색(BM25)은 질문 + 아젠다 키워드, 의미 검색은 질문만(키워드를 섞으면 질문 의도가 흐려짐). 질문이 없으면(버튼 경로) 둘 다 아젠다 키워드. 키워드는 데이터 쪽 설정 파일(`processing/config/agenda_search_terms.json`)에 두고, precheck 판정표(`intent_data_sources.json`)는 지금 자리에 그대로. 토론은 질문만 넘김 | #84 Q3, 11/24 합의 |
| 숫자 표시 | 주장 문장 속 숫자는 `{{metric_id}}`로 쓰고 토론 쪽이 묶음의 `metrics[].display`로 치환. 자리표시자 목록(`metric_ids`)은 `metrics` 중 `value`와 `display`가 둘 다 있는 지표만. 남은 자리표시자는 L1이 잡음 | 토론 기획서 v3.0, #84 Q1 |
| 값이 없는 지표 | 자리표시자 목록에서 빼고, `reason`이 사실 자체인 경우만 문장 근거로 씀(예: `capital_impaired` → "자본잠식") | #84 Q1 |
| 근거 ID | 지표: `metric:{종목}:{지표}:{기준일}`, 블록: `block:{종목}:{블록}:{as_of}`(예: `block:005930:target_price:2026-11-10`). `document_type="structured"`, `title`은 지표·블록 이름, `source`는 함수 이름, `date`는 `as_of`. 블록 ID의 `as_of`는 요청 기준일이 아니라 **블록 자신의 기준일**(예: `flow`가 11/21 값이면 `block:005930:flow:2026-11-21`). 토론이 블록을 짧은 표 문장 하나로 바꿔 근거로 넣고, 기준선 기록에도 남김 | #84 Q2 |
| 비교 모드 | 종목마다 축 단위로 같은 방식(대칭 검색)으로 부름 | 토론 기획서 v3.0 |
| 온톨로지 | 이 묶음에 넣지 않고 `get_ontology_context`로 따로(기능 플래그 뒤) | 토론 기획서 v3.0, ADR 0008 |

**공통 키** (모든 `agent_type`)

| 키 | 내용 |
| --- | --- |
| `ticker`, `agent_type` | 요청한 종목, 에이전트 종류 |
| `intent` | 요청한 아젠다. 없으면 `null` |
| `as_of` | 기준일. 없으면 오늘(한국 시간) |
| `data_tier` | 근거 종류(4-3절). 상태 조회에 실패하면 `null` |
| `error` | 상태 조회 실패나 잘못된 `agent_type`일 때만 문자열 |

**토론 묶음에 모든 intent가 공통으로 갖는 키**

| 키 | 내용 | 출처 |
| --- | --- | --- |
| `metrics` | 그 아젠다의 지표 **목록**. 항목마다 `get_metric` 결과 그대로(`value`, `unit`, `display`, `as_of`, `reason`). 값이 없는 지표도 빼지 않고 `value: null`과 사유를 둠 | `get_metric` |
| `documents` | 문서 검색 결과(`query`, `mode`, `results[]`). 질문이 없어도 아젠다 키워드로 항상 검색. 아젠다당 5개, 문서 종류가 여럿이면 종류별로 최소 1개씩 섞음(예: 리포트 3 + 뉴스 2). 결과가 0건이면 리포트 → 뉴스 → 공시 순으로 한 번 더 넓혀 찾고 `widened: true` 표시 | `search_documents` |

**intent별 지표·블록**

- 지금 묶음에 있는 블록: `target_price`·`financials`·`disclosures`·`macro`·`index`·`sensitivities`(#110). **(예정)** 표시한 계산 근거 블록 4개(`valuation`·`fundamental_trend`·`price_trend`·`flow`)는 `get_derived_snapshot` 실패 처리(#88, 머지됨) 뒤 더합니다. 더할 때 토론 쪽 근거 변환(#120 `structured.py`)에도 요약 문장을 추가해야 해서 미리 알립니다.

| intent | `metrics` (metric_id) | 추가 블록 | 문서 종류 | precheck 데이터가 묶음 어디에 있나 |
| --- | --- | --- | --- | --- |
| `valuation` | `per`, `pbr`, `eps`, `bps`, `roe_ttm`, `operating_margin`, `close`, `market_cap` | `valuation`(예정), `target_price`, `financials`, `price_trend`(예정) | 리포트 | 재무 → `financials`, 시세 → `price_trend`·`close`, 목표가 → `target_price`, 리포트 → `documents` |
| `growth` | `revenue_growth_yoy`, `operating_margin`, `roe_ttm` | `fundamental_trend`(예정), `financials` | 리포트, 뉴스 | 재무 → `financials`, 계산 근거 → `fundamental_trend`, 리포트·뉴스 → `documents` |
| `risk` | `debt_ratio`, `short_volume_ratio_20d`, `short_balance_ratio`, `insider_net_shares_90d`, `insider_sell_reports_90d`, `major_holder_ratio_change_90d`, `foreign_net_buy_20d` | `price_trend`(예정), `disclosures` | 리포트, 뉴스, 공시 | 수급·지분공시 → `metrics`, 공시 → `disclosures`·`documents`, 뉴스·리포트 → `documents` |
| `flow` | `foreign_net_buy_20d`, `inst_net_buy_20d`, `individual_net_buy_20d`, `short_volume_ratio_20d`, `short_balance_ratio` | `flow`(예정) | 뉴스 | 수급 → `flow`·`metrics` |
| `shareholder_return` | `dividend_yield`, `dps`, `eps`, `close` | `disclosures`(주주환원 공시만) | 리포트, 공시 | 공시 → `disclosures`, 시세 → `close`·`dividend_yield`, 리포트 → `documents` |
| `macro` | (없음) | `macro`, `index`, `sensitivities` | 리포트, 뉴스 | 민감도 → `sensitivities`, 뉴스·리포트 → `documents` |

**아젠다 키워드 (초기값, `processing/config/agenda_search_terms.json`, #84 Q3)**

| intent | 키워드 |
| --- | --- |
| `valuation` | 실적 밸류에이션 목표주가 |
| `macro` | 업황 금리 환율 |
| `risk` | 리스크 우려 하락 |
| `growth` | 성장 신사업 증설 수주 |
| `shareholder_return` | 배당 자사주 주주환원 |
| `flow` | 외국인 기관 수급 순매수 |

**블록 모양과 개수 상한**

| 블록 | 모양 | 개수 상한 | 출처 |
| --- | --- | --- | --- |
| `valuation` **(예정)** | PER·PBR 과거 백분위, 업종 중앙값 대비 | – | `get_derived_snapshot`의 `valuation` |
| `fundamental_trend` **(예정)** | 분기 매출·영업이익·순이익 YoY·QoQ | – | `get_derived_snapshot`의 `fundamental_trend` |
| `price_trend` **(예정)** | 수익률, 최근 1·3개월 실현 변동성, 52주 위치, 지수 대비 | – | `get_derived_snapshot`의 `price_trend` |
| `flow` **(예정)** | 5일 순매수, 시가총액 대비 등 **`metrics`에 없는 값만**(20일 순매수·공매도는 `metrics`) | – | `get_derived_snapshot`의 `flow` |
| `target_price` | 컨센서스(최근 180일), 목표주가 상승여력(컨센서스 ÷ 종가 − 1), 최근 의견 목록(`broker_key` 포함) | 의견 최근 10건 | `get_target_price_data` |
| `financials` | 분기 재무(연결/별도 표시) | 최근 8분기 | `get_financials` |
| `disclosures` | 공시 목록 + 수집 시작일(`coverage_from`) | 리스크: 최근 90일 10건, 주주환원: 최근 1년 10건 | `get_disclosure_data` |
| `macro` | 지표별 시계열(지표마다 기준일 표시). 이 종목의 민감도 요인부터: 국고채 3·10년, 원/달러, 기준금리, 소비자물가, 브렌트유, D램 수출물가 | 일별 최근 60거래일, 월별 최근 13개월 | `get_macro_data` |
| `index` | 코스피·코스닥 일별 종가 | 최근 60거래일 | `get_index_data` |
| `sensitivities` | **시장 효과를 뺀 값만**(`adjusted`, `certain`, `q_value`)과 기준일. 원래 상관(`raw`)은 넣지 않음(ADR 0011은 시장 효과를 빼지 않은 관계를 노출하지 않음). 코스피는 시장 자체라 시장 효과를 뺀 값이 없어 빼고, 시장 베타는 시뮬레이션이 `sensitivities` 표에서 씀 | 일별 3(국고채 3·10년, 원/달러), 월별 3(브렌트유, 소비자물가, D램 수출물가) | `get_sensitivities` |

- `get_derived_snapshot`은 한 번만 부르고, 아젠다에 필요한 블록만 꺼냅니다(종목당 약 1초).
- **같은 숫자를 두 군데 두지 않습니다.** 블록에는 `metrics`에 없는 값만 둡니다. 숫자 출처가 둘이면 치환 값과 근거 문장이 어긋날 수 있습니다(#84 Q4).
- `sensitivities`에는 주의 문구를 같이 넣습니다: "월별 상관은 함께 움직인 정도이고 인과가 아님". 엣지 노출 여부는 온톨로지(`get_ontology_context`)가 따로 판단합니다.
- 예상 시간: 아젠다 하나에 약 1.5–3초. 토론이 `data_status`를 넘기면 상태 조회(0.3–1초)는 빠집니다.

**예시** (`intent="flow"`, `flow` 블록은 예정 모양)

```jsonc
{
  "ticker": "005930", "agent_type": "debate", "intent": "flow",
  "as_of": "2026-11-23", "data_tier": "report", "error": null,
  "metrics": [
    {"metric_id": "foreign_net_buy_20d", "value": -1169095241800.0, "unit": "원",
     "display": "-1.17조 원", "as_of": "2026-11-21", "reason": null},
    {"metric_id": "short_balance_ratio", "value": null, "unit": "%", "display": null,
     "as_of": "2026-11-19", "reason": "partial_window"}
  ],
  "flow": {"foreign_net_buy_5d": 0, "...": "...", "as_of": "2026-11-21"},   // (예정) metrics에 있는 값은 두지 않음
  "documents": {"query": "외국인 매도 이유 외국인 기관 수급 순매수", "mode": "hybrid", "widened": false,
                "results": [{"chunk_id": "…", "doc_id": "…", "document_type": "news", "title": "…",
                             "author_org": "…", "date": "2026-11-20", "url": "…", "content": "…"}]}
}
```

**다른 경우**

| 경우 | 반환 |
| --- | --- |
| 토론, `intent` 없음 | 지금과 같음: 목표가, 매크로, 문서(`query`가 있을 때) + 공통 키. 토론은 아젠다마다 `intent`를 넘기므로 이 경우는 쓰지 않음 |
| 시뮬레이션 | 시세, 매크로, 목표가 + 지수(`index_daily`, 최근 3년)와 파라미터 기준일(`sim_params_as_of`) 추가 예정 |
| 트렌드 리포트 | 목표가, 시세, 매크로, 리포트·뉴스 후보 각 15개. `intent`는 쓰지 않음 |

**확인할 것**

| # | 질문 | 누구 |
| --- | --- | --- |
| ~~Q1~~ | 자리표시자 목록을 묶음 `metrics`에서 → **해결:** 네. `value`·`display`가 둘 다 있는 지표만, 치환은 토론 쪽 | 유민 |
| ~~Q2~~ | 지표·재무 근거 ID → **해결:** `metric:{종목}:{지표}:{기준일}`, 블록은 `block:{종목}:{블록}:{as_of}` | 유민 |
| ~~Q3~~ | 검색어 → **해결:** 키워드 검색은 질문 + 아젠다 키워드, 의미 검색은 질문만, 질문이 없으면 키워드. 키워드는 데이터 쪽 설정 파일 | 유민 |
| ~~Q4~~ | 지표·블록 목록 → **해결:** 목록은 그대로, 민감도는 시장 효과 뺀 값만, 중복 숫자 없음, 문서 종류별 최소 1개, 목표주가 상승여력 추가 | 유민 |
| Q5 | `metrics`와 블록 이름을 계약서 `GetAgentContextOutput`에 적을지(계약 draft.6과 함께) | 태은 |

### 4-3. data_tier (근거 종류)

`intent`와 상관없이 항상 붙습니다. 위에서부터 있는 것을 씁니다.

| 값 | 뜻 |
| --- | --- |
| `report` | 애널리스트 리포트가 있음 |
| `news_only` | 리포트가 없어 뉴스로 대체 |
| `disclosure_only` | 뉴스도 없어 공시로 대체 |
| `derived_only` | 시세·재무로 계산한 근거로 대체 |
| `macro_only` | 매크로 지표만 있음 |

## 5. 온톨로지 입력값

온톨로지 시드의 데이터 칸은 손으로 옮기지 않고 같은 방식으로 다시 계산합니다(`python -m crawling.ontology_inputs <명령>`). 노출 여부와 가설은 온톨로지(유민)가 정합니다.

| 명령 | 계산하는 것 | 결과 |
| --- | --- | --- |
| `sensitivities` | 종목·섹터 × 지표의 원래 상관과 **시장 효과를 뺀 상관**, 95% 구간, 방향 확실 여부, q값 | 섹터 → 매크로 엣지는 기준 통과 0개(19개 기각). 종목 → 매크로는 가설 있는 10개를 시드가 판정(시드 v0.10, #80) |
| `sector-grades` | 섹터 금리·환율 등급 후보 | 노출하지 않기로 함 |
| `macro-direction` | 지표가 오를 때 시장이 같이 움직였는지 | 4개 확정(시드 v0.8) |
| `impacts` | 지표끼리의 방향(기준금리 사건 분석, 1달 시차 상관) | 1개 확정(소비자물가 → 기준금리) |
| `kind` | KRX KIND 업종·주요제품으로 세부 업종·지주사 후보, 확정값과 차이 표시 | 세부 업종 34개·지주사 19개 확정 |
| `monthly --save` | 위 계산을 매달 한 번에. 민감도는 `ontology_sensitivity_inputs` 표에 기준일별로 쌓음 | 11/23 값 765행 저장 |

- 계산 방법: 일별은 최근 3년, 종목 수익률과 지표 변화에서 각각 코스피 효과를 뺀 상관. 월별은 최근 최대 120개월, t월 주가와 t+1월 지표 변화, 시장은 핵심 종목 동일가중 평균(그 종목 자신 포함). 95% 신뢰구간(Fisher). q값은 두 가지: 가설 엣지끼리(시드가 계산), 지표별 전체 종목(이 표의 `q_value`). 모두 Benjamini-Hochberg.
- 시드는 표를 직접 읽거나 다시 계산하지 않고, `ontology_sensitivity_inputs`에서 내보낸 기준일 스냅샷 CSV(`computed_at` 포함)를 읽어 노출 기준 4개를 판정합니다. 두 달 연속 탈락은 직전 기준일 CSV로 판정합니다(시드 v0.10, #80). 데이터 쪽은 매달 표에 값을 쌓는 것까지 합니다.
- 노출 기준과 운영 규칙: [ADR 0011](../decisions/0011-ontology-sensitivity-exposure.md)(#79)

## 6. 저장소 (Supabase)

### 6-1. 테이블

| 종류 | 테이블 | 내용 | 지금 (11/23) |
| --- | --- | --- | --- |
| 종목 | `companies` | 종목 정보(이름·별칭·WICS 업종·티어·우선주) | ✅ 2,867종목(업종 빈 종목 299) |
| 문서 | `document_chunks` | 리포트·뉴스·공시 조각과 임베딩 | ✅ 리포트 19,490 · 뉴스 14,527 · 공시 1,755 조각 (11/24) |
| 문서 | `report_metadata` | 리포트 목록과 처리 상태 | ✅ 완료 1,125 · 대기 0 · 실패 12 · 본문 없음 71 (11/24) |
| 문서 | `news_metadata` | 뉴스 기사 | ✅ 8,550건, 90일 보관. **11/10–11/19는 보류** |
| 문서 | `disclosure_metadata` | DART 수시공시 | ✅ 838건, 8/11부터 |
| 시세 | `price_data`, `market_daily`, `index_daily` | 수정주가, PER·PBR 등, 지수 | 🟡 T1만, 3년(11/23까지) |
| 수급 | `investor_flow_daily` | 투자자별 순매수, 공매도 | ✅ T1, 3년 |
| 재무 | `financials` | 분기 재무(정정공시 이력 보관) | ✅ 3분기 실적(11/19 접수분)까지 |
| 지분 | `insider_holdings` | 대량보유, 임원·주요주주 지분 변동 | ✅ T1 보통주 98종목 |
| 목표가 | `broker_opinions` (+ 분할 환산 뷰) | 증권사 목표가·의견(KIS) | ✅ T1 98종목, 12개월 |
| 매크로 | `macro_data` | 13개 지표: 기준금리, 국고채 3·10년, 소비자물가, 원/달러, 유가 3종, 수출·수입·무역수지, 산업생산, D램 수출물가 | ✅ 2000년부터 |
| 시뮬레이션 | `sim_params` | GARCH 파라미터 | ✅ 매달. 정상 95 · 수렴 실패 4 · 이력 부족 1 |
| 시뮬레이션 | `sensitivities`, `monthly_correlations` | 일별 민감도(코스피·원/달러·국고채 3·10년), 월별 상관(유가·물가·D램) | ✅ 매달 |
| 온톨로지 | `ontology_sensitivity_inputs` | 시장 효과 뺀 민감도를 기준일별로 | ✅ 765행 |
| 평가 | `search_golden_set` | 검색 골든셋 | ✅ 30문항 |
| 작업 | `collection_jobs`, `promotion_demand` | T2 수집 상태, 승격 수요 | Post-MVP |

- 모든 핵심 테이블에 RLS를 켜고, 공개 키의 쓰기 권한을 막았습니다.
- **DB 용량은 약 454MB / 무료 한도 500MB입니다(11/24).**

### 6-2. `document_chunks` 주요 컬럼

| 컬럼 | 설명 |
| --- | --- |
| `chunk_id` | `{문서 ID}:{본문 해시 앞 12자}`. 다시 처리해도 같은 내용이면 같은 ID(온톨로지·토론 근거가 참조) |
| `doc_id`, `document_type` | 문서 ID, 종류(`report` / `news` / `disclosure`) |
| `ticker`, `mentioned_tickers` | 대상 종목, 본문에 언급된 종목들 |
| `broker`, `title`, `url`, `published_at` | 증권사, 제목, 원문 주소, 게시일 |
| `section_type`, `chunk_type`, `table_structure` | 구분(요약·본문·면책), 글/표, 표 구조가 살아 있는지 |
| `body`, `embedding`, `search_tokens` | 본문, 임베딩(1024차원), 키워드 검색 색인 |
| `is_active` | 다시 처리해서 사라진 조각은 지우지 않고 `false`(근거 링크 유지) |

## 7. 파싱 · 청킹 (리포트)

| 단계 | 방식 |
| --- | --- |
| 파서 | PyMuPDF(무료). Upstage Document Parse는 비용(6개월 치 약 115–340달러) 때문에 기본에서 뺌 |
| 자르기 | 소제목 기준으로 섹션을 나누고, 섹션 안에서 1,200자 이하로 묶음. 400자보다 짧은 조각은 이웃과 합침 |
| 줄바꿈 | 한국어 리포트의 글자 단위 줄바꿈을 이어 붙여 문장을 복원 |
| 표 | 표 제목·단위와 함께 따로 둠. 구조가 깨진 표(`text_only`)는 **숫자를 표에서 가져오지 않고 DB 값** 사용 |
| 차트 | 축 값·작은 수익률 표는 따로 모아 기본 검색에서 뺌 |
| 반복 문구 | 머리말·꼬리말은 버리고, 면책 문구·의견 이력표는 `disclaimer`로 표시해 기본 검색에서 뺌 |
| 다시 적재 | 대기·실패 리포트만 처리. 이미 처리한 리포트는 건너뜀 |

- 뉴스·공시는 문단 단위로 자르고, 본문에 언급된 종목을 붙입니다.

## 8. 검색

1. **필터 먼저:** 종목, 기간, `as_of`, 면책 제외를 먼저 걸고 그 안에서 점수를 냅니다. 엉뚱한 회사·기간의 문서를 가져오지 않는 게 가장 중요합니다.
2. **키워드(BM25):** 질문과 조각을 같은 한국어 형태소 규칙(Kiwi)으로 잘라 점수를 냅니다.
3. **의미 검색:** 질문 임베딩과 조각 임베딩의 유사도로 찾습니다.
4. **하이브리드(기본):** 두 결과를 합칩니다(RRF). 질문 임베딩이 실패하면 키워드 검색으로 대신합니다.

**골든셋 결과 (30문항)**

| 방식 | nDCG@10 | Hit@10 |
| --- | --- | --- |
| 키워드(BM25) | 0.51 | 0.90 |
| 의미 검색 | 0.52 | 0.90 |
| 하이브리드 | **0.61** | 0.97 |

- 나중에 시험할 것: 리랭커, 표 요약을 검색 열쇠로 쓰기, 증권사 실적 추정표 추출.

## 9. 평가

| 평가      | 내용                          | 목표                             | 상태                 |
| ------- | --------------------------- | ------------------------------ | ------------------ |
| 검색 골든셋  | 질문 + 정답 조각(질문 유형 6가지, 아젠다별) | 하이브리드 nDCG@10 0.61 이하로 떨어지지 않게 | ✅ 30문항(14문항 사람 검토) |
| 시점 누출   | `as_of` 뒤 데이터가 섞이는지 자동 검사   | 0건                             | ✅ 테스트에 포함          |
| 실패 표시   | 조회 실패를 "없음"으로 돌려주는 함수       | 0개                             | 🟡 남은 함수는 #88·#91 리뷰 중 |
| 종목 해석셋  | 정식명·별칭·초성·우선주·오타 약 100건     | 후보에 정답 포함 95% 이상               | ❌                  |
| 목표가 검수셋 | KIS 목표가 30\–50건을 리포트 원문과 대조 | 불일치 거의 0건                      | ❌                  |

- 골든셋 원본은 리포트 내용이 들어 있어 git에 올리지 않습니다.

## 10. 정기 적재와 비용

| 언제 | 무엇 |
| --- | --- |
| 평일 19:30 | 시세·지수, 수급·공매도, 목표가, 지분공시, 매크로, 공시(임베딩 포함). 재무는 월요일만 |
| 매달 1일 20:00 | 민감도·시뮬레이션 파라미터, 월별 상관, 온톨로지 입력값 계산·저장 |
| 기본은 끔 | 리포트·뉴스 적재(DB 용량). 레포 변수로 켬 |

- GitHub Actions 워크플로로 돌립니다. 비밀값 등록과 리뷰가 끝나면 머지합니다.
- **비용:** Supabase 무료 한도(500MB) 중 약 454MB(11/24). T0 전 종목 적재와 시연 기간에는 Pro(월 25달러, 8GB)가 필요합니다. 임베딩은 T1 6개월 치 약 2달러, 이후 매달 약 0.5달러.

## 11. 제거·변경하는 코드

| 파일·필드 | 변경 |
| --- | --- |
| `get_price_data`의 `volatility_30d` | 인사이트보드·시뮬레이션이 `get_derived_snapshot`의 변동성으로 옮기면 제거(임시 호환) |
| `search_documents`의 `report_id` | `doc_id`와 같은 값. 다른 에이전트가 `doc_id`로 옮기면 제거 |
| `document_type="macro_summary"` 별칭 | 매크로 문서가 없어 검색하지 않음. 호출부가 정리되면 제거 |
| `processors/pdf_processor.py` | 예전 청커. 적재는 새 청커(`report_chunker.py`)를 쓰고, 남은 호출부가 없으면 제거 |
| 서버 날짜(`date.today()`) 기본값 | 한국 날짜(`today_kst()`)로 변경 (#55) |

## 12. 미결 사항

| # | 내용 | 상대 |
| --- | --- | --- |
| Q1 | DB 용량: Supabase Pro로 갈지. 가면 T0 정형 데이터, 뉴스 빈 기간, 매일 리포트·뉴스 적재를 켬. 무료로 남으면 뉴스 90일 보관 + 리포트·뉴스는 손으로 적재 | 전원 |
| Q2 | intent별 묶음 모양(4-2절): #84 Q1–Q4는 유민 답으로 정함. Q5(계약서 `GetAgentContextOutput`에 적을지)만 남음 | 태은 |
| ~~Q3~~ | 근거 조각 보존 규칙 → **정함:** `document_chunks` 행은 지우지 않고(비활성만), 나중에 지우게 되면 온톨로지 ISSUE 근거·기준선 기록·토론 결과의 청크 ID는 빼고 지움. 지표·블록 ID는 같은 `as_of`로 다시 만들 수 있지만 값도 같이 남기는 게 안전(`crawling/README.md` "근거 조각 보존 규칙") | 유민 |
| Q4 | 변동성 공용 용어("최근 1개월 실현 변동성", "시뮬레이션 변동성(GARCH)") | 태은, 유민 |
| Q5 | 월별 지표 공개 시차: 지금은 그 달 기준으로 자르고 실제 공개일은 반영하지 않음. 필요해지면 공개일 칸 추가 | 유민 |

## 13. 남은 작업

| 일 | 담당 | 상태 |
| --- | --- | --- |
| 함수 계약 추가(`doc_id`, `broker_key`, `coverage_from`, `get_agent_context`의 `as_of`) | 수경 | ✅ #75 |
| `suggest_alternatives` 머지 | 수경 (리뷰: 태은) | 🟡 #85 리뷰 중 |
| 실패 표시(`resolve_company` 등, `extract_company_mentions`), 한국 날짜, `get_derived_snapshot` 묶음 문제 | 수경 | 🟡 #88·#90·#91 리뷰 중(#55, 12/6까지) |
| 지분공시 지표(수집 전 기간·증감 0 보고), 월별 상관 `as_of` 문서화, 조사 5건(정정보고 중복 아님, 무상증자는 알려진 한계 등) | 수경 | 🟡 #111 리뷰 중 |
| 적자 기업 PER·EPS 사유(`loss_making`) | 수경 | ✅ #113 |
| `get_derived_snapshot` 표본 부족, `is_latest` 뷰(마이그레이션), 지배주주 순이익 적재 | 수경 | ❌ |
| 아젠다 키워드 검색, 문서 종류별 몫·한 문서 2조각 | 수경 | ✅ #106 |
| 아젠다별 지표 목록(`metrics`)과 지표 근거 ID | 수경 | ✅ #108 |
| 지수·민감도 조회 함수(`get_index_data`, `get_sensitivities`) | 수경 | ✅ #109 |
| 묶음 블록(`target_price`·`financials`·`disclosures`·`macro`·`index`·`sensitivities`), 블록 근거 ID, `evidence_id` → `chunk_id`, 문서 넓혀 찾기, 컨센서스 최근 의견 수 | 수경 | ✅ #110 |
| 계산 근거 블록(`valuation`·`fundamental_trend`·`price_trend`·`flow`) | 수경 | ❌ #88 머지 뒤 |
| 과거 시점 `data_tier`, 묶음 속도(연결 공유·병렬, #111 머지 뒤 다시 잼) | 수경 | ❌ |
| 목표가 방향 라벨 경계값 상수 | 수경 | ❌ #82 ADR 뒤 |
| `simulation_ready`를 기준일로 판정(`as_of`) | 수경 | 🟡 #103 리뷰 중 |
| `broker_key` 보강(`(주)` 떼기, 예외 사전 적용 기간), `chunk_type` 인자 | 수경 | 🟡 #112 리뷰 중 (컨센서스 `broker_key` 묶기·`revisions`는 ✅ #105, `DataStatus` 한국 날짜는 ✅ #75) |
| 근거 조각 보존 규칙 문서(12절 Q3) | 수경 | 🟡 #114 리뷰 중 |
| 평가셋: 종목 해석셋, 목표가 검수셋(9절) | 수경 | ❌ |
| 남은 리포트 적재(11/9–11/17 117건) | 수경 | ✅ 11/24 완료. 7건은 PDF를 자르다 멈춤(PyMuPDF 오류), 따로 확인 필요 |
| 뉴스 빈 기간(11/10–11/19) 채우기 | 수경 | ❌ DB 용량(Q1) 결정 뒤 |

## 14. 근거 자료

조사 근거 대부분은 영어·미국 공시 데이터이고, 일부는 해당 기술을 파는 회사의 실험입니다. 숫자는 방향으로만 보고, 최종 판단은 우리 골든셋으로 합니다.

- 에이전트 API 계약 명세: `docs/api/openapi.yaml`
- FinanceBench (공시 저장소 분리 여부에 따른 정답률 19% / 50%): arxiv.org/abs/2311.11944
- 금융 보고서 요소 기반 청킹 (53.19% vs 고정 길이 48.23%): arxiv.org/abs/2402.05131
- T²-RAGBench (표를 요약문으로 바꾸면 숫자 답변 저하): arxiv.org/abs/2506.12071
- FinRAGBench-V (리서치 리포트 차트, 이미지 검색 vs 텍스트 검색): arxiv.org/abs/2505.17471
- 카카오뱅크 금융보안 AI 챌린지 후기 (형태소 BM25, 정규화 +4.5%p): tech.kakaobank.com
- 미래에셋증권 GraphRAG 발표 요약 (용어 매핑 45% → 65%): 블로터 2026-08-27
- pgvector 필터·차원 상한: github.com/pgvector/pgvector
- Upstage 임베딩 문서 (passage/query, 구버전 별칭 종료): console.upstage.ai
