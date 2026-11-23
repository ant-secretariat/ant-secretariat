# 오케스트레이터(Agent C) 기획서

| 항목 | 값 |
| --- | --- |
| 버전 | **v2.1** (2026-11-23) |
| 상태 | 검토 중 |
| 담당 | 태은 |
| 상위 문서 | [헌법](../../.specify/memory/constitution.md) > [ADR](../decisions/) > PRD v1.6 > 기능 명세서 v0.8 > 이 문서 |
| 계약 | [`docs/api/openapi.yaml`](../api/openapi.yaml) `1.0.0-draft.5` |
| 구현 계획 | [`specs/001-orchestrator-trend-insight/`](../../specs/001-orchestrator-trend-insight/plan.md) |

## 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1.0 | 2026-10-13 | Notion "오케스트레이터 & 에이전트 아키텍처 설계 초안" |
| v1.1 | 2026-11-05 | Notion "시그니처 계약" (봉투·`resolve_entities`·플래너 시그니처) |
| v2.0 | 2026-11-23 | 저장소로 이관. 레포 현황에 맞춰 수정: 자유 질의·플래너를 Post-MVP로, 2종목 비교(ADR 0007)·SSE(ADR 0009)·Problem 오류(#60) 반영, 작업 저장소를 Supabase로 |
| **v2.1** | 2026-11-23 | #68 리뷰 반영: 경로별 실행 조건(5.3, 선언형 표), 커버 판정을 `data_status.sources`로, precheck에 `data_status` 전달, 거절 payload는 오케스트레이터가 채움, `append_event` 직렬화, 시뮬레이션 시작 흐름(6.3), 보관 기간·연결 풀 |

### v1.1 → v2.0 무엇이 바뀌었나

| 항목 | v1.1 (Notion) | v2.0 | 근거 |
| --- | --- | --- | --- |
| 자유 질의(채팅)·플래너 | 1차 릴리스 포함 | **Post-MVP.** MVP는 버튼 경로 3개 | 계약서 11/5 결정 |
| 도구 레지스트리 | 우선순위 1 | **Post-MVP.** 플래너가 생길 때 함께. MVP 에이전트는 데이터 함수를 직접 호출 | 레지스트리를 쓰는 쪽(플래너·후속 질문)이 MVP에 없음 |
| 공통 봉투 `envelope.py` | "구현 완료, 커밋 안 함" | 어느 브랜치에도 없음(계약 OQ-1). **`backend/contracts/envelope.py`로 새로 구현**, `REASON_POLICY` 표를 이 문서 4장에 확정 | 계약 OQ-1 |
| 오류 응답 | 설계만 | `core/errors.py`(#60)에 Problem 구현됨. 사유 정책을 봉투와 같은 표로 합침 | #60 |
| 종목 해석 | `resolve_company`의 `matched` | `status`(exact·ambiguous·not_found) + `error`. 문장 속 종목은 `extract_company_mentions` | #32, #60 |
| 토론 비교 | D3 별도 | 토론 요청 종목 1~2개, 3개 이상·한쪽 미커버 거절 | ADR 0007 |
| 진행 상황 전달 | `pg_notify` | `job_events` 1초 조회 SSE | ADR 0009 |
| 작업 저장소 | SQLite `agent_jobs` | Supabase `agent_jobs`·`job_events` (마이그레이션 신규) | ADR 0005, 0009 |
| precheck 입력 | `query`, `companies` | + `company_mentioned`(= `EntityResolution.mentioned_in_query`) | #46 |

## 1. 역할과 범위

오케스트레이터는 FE 요청을 받아 **종목을 확정하고(관문1), 필요한 사전 판정을 거쳐, 맞는 에이전트를 부르고, 결과를 공통 봉투로 돌려준다.** 분석 자체는 하지 않는다.

**MVP 범위 (버튼 경로)**

| 경로 | 엔드포인트 | 호출 대상 | 실행 방식 |
| --- | --- | --- | --- |
| 인사이트보드 | `POST /orchestrate/insight-board` | Agent E | 동기, `ok`·`partial`·`rejected` |
| 트렌드 리포트 | `POST /orchestrate/trend-report` | Agent D | 동기, `ok`·`partial`·`rejected` |
| 토론 | `POST /orchestrate/debate` | precheck → Agent F (→ G) | job 생성 후 즉시 `job_started`, 진행은 SSE |
| 진행 상황 | `GET /jobs/{job_id}/events` | `job_events` | SSE, 1초 조회 |

**Post-MVP:** `POST /orchestrate/chat`, `.../clarify`, 플래너(`make_plan`·`validate_plan`·`execute_plan`), 도구 레지스트리, Langfuse 트레이스, 근거 부족 루프의 S4~S5. 설계는 9장에 남겨 둔다.

## 2. 설계 원칙: 제한된 자율성

v1.0의 원칙을 유지한다. "실행 경로는 정해진 코드가, 사실(숫자·출처·기준일)은 데이터가 정한다. LLM은 설명만 쓴다."

| 판단 지점 | 방식 | 이유 |
| --- | --- | --- |
| 라우팅 (버튼) | `request_type` 그대로 | 사용자의 버튼이 이미 의도를 정함 |
| 종목 해석 | 룰 (`resolve_company`·`extract_company_mentions`) | 틀리면 다른 종목을 분석함. 애매하면 사람에게 되묻기 |
| 토론 사전 판정 | 룰 (`precheck`, 유민) | job 생성 전 100ms 안에 거절 |
| 숫자·방향·배지 | 코드 | 숫자 환각 차단 (헌법 원칙 IV) |
| 설명 문장 | LLM 1회 + L1 검증 | 열린 입력이라 LLM이 필요, 결과는 기계 검증 |

## 3. 요청 흐름

```text
FE ── 세션 쿠키 ──▶ API (api/orchestrator.py)        HTTP 입력 → OrchestratorRequest
                     │  user_id는 세션에서 주입 (바디 필드 없음)
                     ▼
              [C] run_orchestrator_request
                     │
       ① 관문1  resolve_companies(inputs, query, max_companies)          종목 확정 (5.1·5.2)
                     │   not_found·ambiguous → rejected company_not_found
                     │   too_many / partial_covered → rejected (토론만)
                     │   check_coverage(data_status, ROUTE_REQUIREMENTS[경로])   실행 조건 (5.3)
                     │     uncovered → rejected uncovered_company / no_data → rejected no_data (+ 대안 3개)
                     │   조회 실패(resolve_company·data_status) → 503 upstream_unavailable (Problem)
                     │   거절이면 log_uncovered_query(gate=1)
                     ▼
       ② 라우팅  decide_route(request)  ── insight_board ──▶ [E] run_insight_board ──▶ Envelope
                     │                   ── trend_report  ──▶ [D] run_trend_report  ──▶ Envelope
                     │                   ── debate
                     ▼
       ③ 토론    precheck(query, companies,                              [F, 유민]
                     │            data_status=<관문1의 data_status로 만든 provider>,
                     │            company_mentioned=<5.2>)
                     │   reject → rejected (사유 코드는 precheck, payload는 오케스트레이터가 채움, 4.1)
                     │            + log_uncovered_query(gate=2·3)
                     │   DataStatusUnavailable → 503 upstream_unavailable (조회 실패 ≠ 데이터 없음)
                     ▼
       ④ job     find_reusable_job(user, tickers, query)  → 있으면 job_started reused=true
                     │   진행 중 job이 한도 이상 → 409 concurrent_job_limit (Problem)
                     │   create_job → job_events(job_started) → 백그라운드 run_debate
                     ▼
              job_started {job_id, reused:false}
```

- 인사이트보드·트렌드 리포트는 precheck를 거치지 않는다. 관문1의 실행 조건(5.3)만 통과하면 실행하고, 데이터가 적으면 범위를 줄인다(계약: "T0·T2는 거절하지 않고 축소 실행"). 티어는 노출 범위에만 쓰고 거절 기준으로 쓰지 않는다.
- 종목 상태 조회(`get_available_data_status`, 종목당 약 0.3초)는 관문1의 `resolve_company`에서 한 번만 한다. precheck와 실행 조건 판정은 그 결과를 넘겨받는다.
- 오케스트레이터는 하위 에이전트의 결과 내용을 해석하지 않는다. 봉투의 `status`만 정한다.

## 4. 공통 봉투와 사유 정책 (`backend/contracts/envelope.py`)

계약서 Envelope 스키마를 Pydantic으로 그대로 구현한다. **업무 결과는 HTTP 200 + `status`**, **인프라·정책 오류는 4xx/5xx Problem**(#60 `core/errors.py`).

### 4.1 사유 정책표 `REASON_POLICY` (계약 OQ-1 해소안)

사유는 반드시 `make_reason(code, message, **payload)`로 만든다. 정책표가 채널·HTTP 상태·다음 행동을 정하므로 어긋날 수 없다. `core/errors.py`의 Problem도 이 표를 읽도록 바꾼다(지금은 클래스 속성에 흩어져 있음).

| 사유 코드 | 채널 | HTTP | `next_action.type` | payload |
| --- | --- | --- | --- | --- |
| `uncovered_company` | rejected | 200 | `choose_alternative_company` | `alternatives` 3개 (아래 대안 규칙) |
| `no_data` | rejected | 200 | `choose_alternative_company` | `alternatives` 3개 (아래 대안 규칙) |
| `company_not_found` | rejected | 200 | `rephrase_company` | 없음 |
| `too_many_companies` | rejected | 200 | `select_companies` | `candidates` ≥3, `max_select=2` |
| `partial_coverage` | rejected | 200 | `run_single_analysis` | `company` |
| `out_of_scope_topic` | rejected | 200 | `choose_supported_topic` | `topics` ≥1 |
| `data_collecting` | rejected | 200 | `check_back_later` | `ready_at` (선택) |
| `partial_result` | partial | 200 | `retry_failed_parts` | `failed_parts` ≥1 |
| `unauthenticated` | Problem | 401 | `login` | 없음 |
| `invalid_request` | Problem | 422 | `fix_input` | `fields` (선택) |
| `concurrent_job_limit` | Problem | 409 | `view_existing_job` | `job_id` |
| `invalid_job_state` | Problem | 409 | `view_existing_job` | `job_id` |
| `job_not_found` | Problem | 404 | `fix_input` | 없음 |
| `rate_limited` | Problem | 429 | `retry_later` | `retry_after_seconds` + `Retry-After` 헤더 |
| `upstream_unavailable` | Problem | 503 | `retry` | 없음 |
| `internal_error` | Problem | 500 | `retry` | 없음 |

- **payload는 오케스트레이터가 채운다.** precheck는 사유 코드(`out_of_scope_topic`·`data_collecting`·`no_data`)만 돌려준다.
  - `alternatives`: 데이터 함수 `suggest_alternatives(ticker, n=3)`(수경, 계약 draft.6에 추가). 커버 종목 중 **같은 WICS 중분류 → 같은 대분류 → 전체** 순서로 시가총액 큰 순. 요청 종목의 업종이 비어 있으면 바로 전체 시총순.
  - `topics`: 토론이 지원하는 아젠다 목록(`precheck` 설정의 `AGENDA_TITLES`).
- **#60에서 바뀌는 점:** 지금 `CompanyNotFoundError`는 422 Problem이다. 봉투로 옮기면 `company_not_found`는 200 `rejected`가 된다(계약대로). 사용자를 못 찾은 404도 `job_not_found`를 같이 쓰는데, 사용자 조회는 세션 도입 후 401 `unauthenticated`로 바뀌므로 별도 코드를 만들지 않는다.
- `ResponseMeta.trace_id`는 #60의 요청별 `trace_id`를 그대로 쓴다. `data_as_of`는 기본값 없이 각 에이전트가 채운다(없으면 명시적으로 `null`).

## 5. 관문1: 종목 확정

### 5.1 함수

```python
def resolve_companies(
    inputs: list[str],              # FE가 고른 회사 이름·종목코드 (버튼 경로)
    query: str | None = None,       # 토론 질문. mentioned_in_query 판정용
    max_companies: int = 2,         # 인사이트보드 3, 토론·트렌드 리포트 2·1
) -> EntityResolution
```

- 계약의 `resolve_entities(text, max_companies)`는 **자유 질의용**(문장에서 종목 추출)이라 Post-MVP다. 버튼 경로는 FE가 이미 종목을 골라 보내므로 입력 목록을 하나씩 `resolve_company`로 확정하는 `resolve_companies`를 쓴다. 두 함수는 같은 `EntityResolution`을 돌려준다.
- `orchestrator/companies.py`의 `resolve_company_context`(#60)를 이 함수로 대체한다.

### 5.2 판정 규칙

| 순서 | 조건 | `status` | 처리 |
| --- | --- | --- | --- |
| 1 | `resolve_company` 결과에 `error`, 또는 `data_status`가 `None`, 또는 `data_status.error` | — | `UpstreamUnavailableError` (503). "데이터 없음"으로 읽지 않는다 |
| 2 | 입력 개수 > `max_companies` | `too_many` | 토론만 rejected `too_many_companies` |
| 3 | 하나라도 `not_found` | `not_found` | rejected `company_not_found` |
| 4 | 하나라도 `ambiguous` | `ambiguous` | 버튼 경로: rejected `company_not_found` (FE 자동완성이 후보를 이미 보여 주므로). 자유 질의(Post-MVP): `clarification_needed` |
| 5 | 확정됐지만 커버 밖 (5.3의 `uncovered`) | `uncovered` / `partial_covered` | 단일: rejected `uncovered_company`. 비교 한쪽만: rejected `partial_coverage` |
| 6 | 모두 확정·커버 | `ok` | `mode` = 1개 single, 2개 compare. 이어서 5.3 실행 조건 |

- **커버 판정:** 우선주가 아니고, `data_status.sources`에 적재된 소스가 하나라도 있으면 커버다. 지금 `companies` 2,867종목은 모두 티어가 있지만 시세·재무·수급은 T1 100종목만 적재돼 있어(11/23), 티어로는 커버를 가를 수 없다.
- **`mentioned_in_query`:** `extract_company_mentions(query)`로 찾은 ticker 집합과 확정 종목이 하나라도 겹치면 true, 겹치지 않으면 false. precheck의 `company_mentioned`로 넘긴다(#26 별칭 문제 해결).
  - 함수가 빈 목록을 돌려주면 조회 실패와 "언급 없음"을 구분할 수 없으므로 precheck에는 `None`을 넘겨 공식명으로 직접 확인하게 한다(research R13). 계약 필드는 bool이라 응답에는 false로 둔다.
- **precheck 입력:** 관문1의 `data_status`를 `TickerDataStatus`로 바꾸는 provider를 넘긴다. 어댑터는 `debate_renewal` 쪽(유민)에 둔다.
- **계약 불일치:** `EntityResolution.companies`가 `maxItems: 2`인데 인사이트보드는 3개까지다. 계약을 `maxItems: 3`으로 바꾸고 "토론은 2개"를 `max_companies`로 표현한다(계약 PR 필요, 헌법 원칙 II).

### 5.3 경로별 실행 조건 (선언형 표)

종목 확정은 모든 경로가 같고, **"이 경로를 실행하려면 어떤 데이터가 있어야 하는가"만 경로마다 다르다.** 조건은 코드 분기 대신 표로 선언하고, 판정 함수 하나가 모든 경로를 처리한다(Specification 패턴의 파라미터형). 형식은 precheck의 `intent_data_sources.json`(`requires_any`)과 같다.

```python
# backend/orchestrator/requirements.py
ROUTE_REQUIREMENTS = {
    ("insight_board", "price"):      {"requires_any": ["price"]},
    ("insight_board", "disclosure"): {"requires_any": ["disclosure"]},
    ("insight_board", "macro"):      {"requires_any": []},          # 종목 데이터 불필요
    ("trend_report", None):          {"requires_any": ["report", "news", "disclosure", "derived"]},
    # 토론은 precheck가 아젠다별로 판정 (intent_data_sources.json)
}

def check_coverage(data_status: dict | None, requirement: dict) -> Coverage: ...
```

| 판정 | 조건 | 응답 |
| --- | --- | --- |
| `unavailable` | `data_status`가 `None` 또는 `error` | 503 `upstream_unavailable` |
| `uncovered` | `sources`가 모두 0건 (적재되지 않은 T0) | rejected `uncovered_company` |
| `no_data` | 커버 종목이지만 `requires_any`의 소스가 모두 0건 | rejected `no_data` |
| `ok` | `requires_any`가 비었거나 하나 이상 있음 | 실행 |

- 각 행의 조건은 그 에이전트 기획서가 소유한다(트렌드 리포트·인사이트보드 기획서 "실행 조건"). 바꿀 때는 기획서와 이 표를 같은 PR에서 고친다.
- 조건 조합(AND·NOT)이 실제로 필요해지면 평가 함수만 컴포지트 형태로 바꾼다. 표 형식은 유지한다.
- `uncovered`와 `no_data`를 나누는 이유: `uncovered_company`는 T0 수집 우선순위 큐(`uncovered_query_log`)의 입력이고, `no_data`는 커버 종목의 데이터 공백이다. 사용자에게는 둘 다 "대안 종목 고르기"로 같다.

## 6. 토론 job

### 6.1 저장소 (Supabase, 신규 마이그레이션)

```sql
agent_jobs (
  job_id text primary key, user_id text not null, job_type text not null,      -- 'debate'
  mode text not null,                                                           -- single | compare
  tickers text[] not null, query text not null,
  status text not null,                                                         -- JobStatus 7종
  precheck jsonb not null, debate_result jsonb, simulation_result jsonb,
  error_code text, created_at timestamptz, updated_at timestamptz
)
job_events (job_id text, seq int, type text, payload jsonb, created_at timestamptz,
            primary key (job_id, seq))
```

- `JobStatus`는 계약의 7종(`queued`·`running`·`debate_completed`·`simulation_pending`·`simulation_running`·`completed`·`failed`)을 공용 열거형으로 둔다. 비교 모드 job은 `debate_completed`에서 끝난다(ADR 0007).
- `seq`는 그 job을 실행하는 워커 한 곳에서만 매긴다(ADR 0009). `append_event(job_id, type, payload)`가 같은 트랜잭션에서 `pg_advisory_xact_lock(hashtext(job_id))`로 잠근 뒤 `max(seq)+1`을 넣는다.
  - 비교 모드는 종목별 Bull·Bear가 병렬이라 같은 job에 이벤트가 동시에 들어온다. 잠금이 없으면 PK 충돌로 이벤트가 실패한다.
  - 전역 자동 증가 번호는 잠금이 필요 없지만, 커밋 순서가 뒤바뀌면 SSE 클라이언트가 앞 번호를 영영 놓칠 수 있어 쓰지 않는다.
- **보관 기간:** 끝난 job(`completed`·`failed`, 비교 모드 `debate_completed`)의 `job_events`는 7일 뒤 지운다. `agent_jobs` 행과 결과는 남긴다(DB 무료 한도 500MB 중 약 440MB 사용, 11/23).
- `simulation_result`에는 요약(분위수·시나리오별 결과)만 저장한다. 경로 전체는 넣지 않는다.

### 6.2 생성 규칙

- **재사용:** 같은 사용자·같은 종목 집합·같은 질문으로 `queued`·`running` job이 있으면 새로 만들지 않고 `job_started` + `reused=true`(FN-DBT-01).
- **동시 실행 한도:** 사용자당 진행 중 job 1개. 넘으면 409 `concurrent_job_limit` + `view_existing_job`.
- **실행:** MVP는 API 프로세스 안의 `asyncio` 백그라운드 작업이다(지금과 같음). 프로세스가 재시작되면 `running` job은 `failed`로 정리한다(시작 시 1회). 외부 큐는 Post-MVP.
- `run_debate(companies, user_id, query, precheck, job_id)`(계약 `RunDebateInput`)는 유민 소유. 오케스트레이터는 job을 만들고 넘기기만 한다. 레거시 `agents/debate`는 `debate_renewal`이 연결될 때 교체한다.

### 6.3 시뮬레이션 시작 (사용자 버튼)

계약의 `POST /orchestrate/debate/{job_id}/simulate`(#46)를 쓴다. 새 경로를 만들지 않는다.

```text
queued → running ─┬─ (compare) → debate_completed                      종료
                  └─ (single)  → simulation_pending ── 버튼 ──▶ simulation_running → completed
                                       │ 누르지 않으면 여기서 멈춤 (토론 결과는 조회 가능)
running·simulation_running ── 실패 ──▶ failed
```

- 토론 완료 이벤트와 job 조회 응답에 `simulation_ready`(`data_status.simulation_ready`, #53)를 같이 내려 FE가 버튼을 미리 끌 수 있게 한다.
- 버튼 요청 처리:
  - 비교 모드이거나 이미 `simulation_running`·`completed` → 409 `invalid_job_state`
  - 시뮬레이션 파라미터가 없는 종목(정상 95종목 밖) → 200 rejected `no_data`. job을 `failed`로 바꾸지 않는다(끝난 토론까지 실패처럼 보이지 않게)
- 시뮬레이션 봉투의 `data_as_of`는 `sim_params.as_of`다(수경).

### 6.4 진행 상황 SSE (ADR 0009)

- `GET /jobs/{job_id}/events`: 본인 job만. `Last-Event-ID` 다음 `seq`부터 보낸다.
- 1초마다 `job_events`를 조회, 15초마다 `: ping`, 종료 이벤트(`completed`·`failed`, 비교 모드는 토론 완료, 단일 모드는 `simulation_pending` 도달) 뒤 연결을 닫는다.
- 조회할 때만 작은 연결 풀(`psycopg_pool`, 최대 5)에서 연결을 빌린다. 스트림마다 연결을 붙잡거나 1초마다 새로 연결하지 않는다(Supabase 무료 플랜 동시 연결 제한).

## 7. 미커버 로그

```python
def log_uncovered_query(event: UncoveredQueryEvent) -> None
# UncoveredQueryEvent: user_hash, query_masked, gate(1|2|3), reason_code, entity?, sector?
```

- 테이블 `uncovered_query_log` (Supabase, 신규). 커버리지 우선순위 큐의 입력이다.
- `user_hash`는 `HMAC(SESSION_SECRET, user_id)`. `query_masked`는 숫자 6자리 이상·이메일·전화번호를 가린 원문(헌법 원칙 IV: 분석 이벤트에 질문 원문 금지 → 가린 문장만).
- `entity`에는 확정된 종목코드가 있으면 반드시 넣는다(데이터 쪽 T0 수집 우선순위 입력).
- 적재 실패는 요청을 막지 않는다(로그만). 단, 실패 사실은 `logger.error`로 남긴다.

## 8. 인증 (계약 OQ-8, 팀 결정 필요)

- 계약: httpOnly 서명 쿠키 `session`, `user_id`는 바디에 받지 않는다.
- MVP 제안: `POST /users`가 `HMAC(SESSION_SECRET, user_id)` 서명 쿠키를 발급하고, 의존성 `current_user_id()`가 검증한다. 추가 라이브러리 없이 표준 `hmac`으로 구현한다. `SameSite=Lax`, 배포 시 `Secure`.
- 이행 기간에는 바디의 `user_id`도 받되 쿠키가 있으면 쿠키를 우선한다. FE 전환 후 바디 필드를 지운다.

## 9. Post-MVP 설계 (v1.0·v1.1 유지)

아래는 MVP 이후 구현한다. 시그니처는 계약서에 있다.

- **자유 질의 경로:** `resolve_entities` → precheck → `make_plan`(LLM 1회) → `validate_plan` → `execute_plan` → 검증 → 응답 조합. ReAct 대신 plan-then-execute(경로를 미리 검증·로깅).
- **되묻기:** `conversations` 테이블에 `pending_clarification` 저장, `clarify`로 재개.
- **도구 레지스트리:** `ToolSpec`(이름·인자 스키마·비용 등급·허용 호출자·부작용) + `invoke()`에서 인자 검증·권한·트레이스를 한 곳에서 처리.
- **근거 부족 루프 S4~S5**, **L2 함의 판정**, **Langfuse 작업 단위 트레이스**.

## 10. 평가 지표 (MVP)

| 지표 | 측정 | 목표 |
| --- | --- | --- |
| 관문1 정확도 | 종목 입력셋(정확·별칭·애매·미커버·오타) 기대 status 일치율 | ≥ 98% |
| 거절 응답 계약 준수 | 모든 rejected가 정책표의 next_action·payload를 가짐 | 100% (자동 테스트) |
| precheck 경유율 | 토론 job 중 precheck 통과 후 생성된 비율 | 100% |
| 봉투 계약 일치 | 응답이 `openapi.yaml` 스키마 검증 통과 | 100% (계약 테스트) |
| 토론 시작 지연 | 요청 → `job_started` p95 | ≤ 1초 |

## 11. 미결 사항

| # | 내용 | 상대 |
| --- | --- | --- |
| ~~Q1~~ | 커버 판정 기준 → **해결:** 우선주 아님 + 적재 소스 1개 이상, 경로별 조건은 5.3 (#68 리뷰) | 수경 |
| Q2 | 인증 방식 확정 (OQ-8) | 팀 |
| Q3 | `EntityResolution.companies` maxItems 3으로 계약 변경 | 유민·수경 (계약 리뷰) |
| ~~Q4~~ | 대안 종목 규칙 → **해결:** 중분류 → 대분류 → 전체 시총순 3개, `suggest_alternatives`(수경) (#68 리뷰) | 수경 |
| Q5 | 사용자당 동시 job 한도 1개가 데모에 충분한지 | 팀 |
