# Data Model: 오케스트레이터·트렌드 리포트·인사이트보드 MVP

API 스키마의 원본은 [`docs/api/openapi.yaml`](../../docs/api/openapi.yaml)이다. 여기서는 **코드 위치·검증 규칙·저장소·상태 전이**만 적는다. 필드 목록은 계약과 기획서를 따른다.

## 1. 공용 타입 (`backend/contracts/`)

| 타입 | 파일 | 검증 규칙 |
| --- | --- | --- |
| `OkResponse[T]`·`PartialResponse[T]`·`RejectedResponse`·`ClarificationResponse`·`JobStartedResponse` | `envelope.py` | `status`가 판별자. `partial`·`rejected`는 `reason` 필수 |
| `Reason` | `envelope.py` | `make_reason(code, message, **payload)`로만 생성. `REASON_POLICY[code]`의 채널과 다르게 쓰면 `ValueError` |
| `NextAction` | `envelope.py` | 행동별 payload 필수 항목·최소 개수(`alternatives` ≥1, `candidates` ≥3 등) |
| `ResponseMeta` | `envelope.py` | `trace_id`는 `core.logging_setup.trace_id_var`, `data_as_of`는 기본값 없음 |
| `CompanyContext`·`Candidate`·`EntityResolution` | `entities.py` | `companies` ≤3 (계약 draft.6), `mode`는 종목 수에서 계산 |
| `JobStatus` | `jobs.py` | 4종(draft.6). 전이는 4장 |
| `JobEvent` | `jobs.py` | `type`은 계약 enum 13종, 비교 모드 종목별 이벤트는 `payload.ticker` 필수 |

공용 열거형 `AgendaId`·`DataTier`·`Tier`는 `processing.enums`에서 import한다(다시 정의하지 않음, 헌법 원칙 II).

## 2. 에이전트 타입

| 에이전트 | 타입 | 파일 |
| --- | --- | --- |
| 오케스트레이터 | `GateResult`(확정 종목 · 거절 봉투), `UncoveredQueryEvent`. `OrchestratorRequest.request_type` 분기는 없앰(엔드포인트가 경로를 정함, ADR 0015) | `orchestrator/gate.py`, `orchestrator/uncovered.py` |
| 트렌드 리포트 | `TrendReportRequest`, `Claim`, `Evidence`, `TrendCards`, `TrendCardsDraft`(LLM 출력), `BrokerView`, `TargetPriceTrend`, `VerificationSummary`, `TrendReportResult` | `agents/trend_report/schemas.py` |
| 인사이트보드 | `CompanyData`, `Badge`, `Comment`, `FeatureSummary`, `InsightBoardResult` | `agents/insight_board/schemas.py` (신규) |

- `Claim`·`Evidence`는 토론(`debate_renewal/schemas.py`)에도 있다. 계약 필드가 같으면 PR-1에서 `backend/contracts/evidence.py`로 옮겨 공용으로 쓴다. 다르면 유민과 맞춘 뒤 옮긴다(두 정의를 오래 두지 않음).

## 3. 저장소 (Supabase, 신규 마이그레이션)

### `agent_jobs`

| 컬럼 | 타입 | 규칙 |
| --- | --- | --- |
| `job_id` | text PK | `<job_type>_<uuid hex>` |
| `user_id` | text not null | 세션 사용자 |
| `job_type` | text not null | `debate` · `simulation` |
| `debate_job_id` | text FK | 시뮬레이션 job → 원래 토론 job (ADR 0013) |
| `data_as_of` | date | 토론 기준일. 토론 job을 만들 때 KST 오늘로 확정(null 없음). 시뮬레이션 job은 토론 job 값을 복사해 이 날짜로 실행 |
| `mode` | text | 토론만: `single` · `compare` |
| `tickers` | text[] not null | 1~2개, 6자리 문자열 |
| `query` | text | 토론만. 재사용 판정 키에 포함 |
| `status` | text not null | `queued` · `running` · `completed` · `failed` |
| `precheck` | jsonb | 토론만, `PrecheckResult` |
| `result` | jsonb | 토론: `DebateResult`, 시뮬레이션: 요약만 |
| `simulation_ready` | boolean | 토론 완료 시점 값 (시뮬레이션 실행 비율 분모) |
| `trace_id` | text | 생성 요청의 trace id, 워커가 이어 씀 |
| `locked_by` · `heartbeat_at` · `attempts` | text · timestamptz · int | 워커 큐 (R4) |
| `error_code` · `failed_stage` | text | `worker_lost`·`timeout` 등 |
| `created_at` · `updated_at` | timestamptz | |

- 인덱스: `(created_at) where status='queued'` — 워커 꺼내기, `(user_id, created_at desc)` — 토론 내역, **부분 유니크 `(user_id) where status in ('queued','running')`** — 사용자당 진행 중 job 합쳐 1개(ADR 0014).
- 꺼내기: `for update skip locked`(ADR 0012). 전체 SQL은 오케스트레이터 기획서 v2.3 6.1·6.2.
- 재사용 키: `user_id`, `job_type`, 정렬한 `tickers`, `query`(시뮬레이션은 `debate_job_id`), `status in ('queued','running')`.

### `job_events`

| 컬럼 | 타입 | 규칙 |
| --- | --- | --- |
| `job_id` | text FK → `agent_jobs` | |
| `seq` | int | job마다 1부터, `append_event`만 매김 (ADR 0009) |
| `type` | text | `JobEvent.type` |
| `payload` | jsonb | |
| `created_at` | timestamptz | |

- PK `(job_id, seq)`. `append_event`가 `pg_advisory_xact_lock(hashtext(job_id))`로 직렬화한다(research R15). 그래도 충돌하면 PK 위반으로 드러난다(조용히 덮지 않음).
- 보관: 끝난 job의 이벤트는 7일 뒤 삭제. `agent_jobs` 행과 결과는 유지.
- `simulation_result`는 요약(분위수·시나리오별 결과)만 저장.

### `uncovered_query_log`

| 컬럼 | 타입 | 규칙 |
| --- | --- | --- |
| `id` | bigint identity | |
| `ts` | timestamptz | |
| `user_hash` | text | `HMAC(SESSION_SECRET, user_id)` |
| `query_masked` | text | 숫자 6자리 이상·이메일·전화번호 가림 |
| `gate` | smallint | 1·2·3 |
| `reason_code` | text | `ReasonCode` |
| `entity` · `sector` | text | null 허용 |

RLS: 세 테이블 모두 서비스 키 전용(익명 접근 없음). `core_tables_rls.sql`과 같은 방식.

## 4. 상태 전이 (job마다 같은 4종)

```text
토론 job       queued → running → completed (단일·비교 모두)  /  failed
                                     │ completed payload: simulation_ready
                                     ▼ 사용자 버튼 (simulation_ready=true)
시뮬레이션 job  queued → running → completed / failed       (debate_job_id = 토론 job)
```

- 버튼: `POST /orchestrate/debate/{job_id}/simulate`(계약 #46)가 시뮬레이션 job을 만들어 `job_started`를 돌려준다. 비교 모드·토론 미완료면 409 `invalid_job_state`, `simulation_ready=false`면 200 rejected `no_data`, 진행 중 시뮬레이션 job이 있으면 `reused=true`.
- `running` → `failed`: 실행 실패, 타임아웃(`timeout`), 워커 중단(`worker_lost`).
- 계약 `JobStatus` 7종을 4종으로 줄이는 변경은 draft.6(contracts C11).

- 상태가 바뀔 때마다 대응 이벤트를 `job_events`에 같은 트랜잭션으로 남긴다(`job_started`, `completed`, `failed`, `simulation_*`).
