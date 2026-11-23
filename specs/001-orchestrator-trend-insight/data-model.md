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
| `JobStatus` | `jobs.py` | 7종. 전이는 3장 |
| `JobEvent` | `jobs.py` | `type`은 계약 enum 13종, 비교 모드 종목별 이벤트는 `payload.ticker` 필수 |

공용 열거형 `AgendaId`·`DataTier`·`Tier`는 `processing.enums`에서 import한다(다시 정의하지 않음, 헌법 원칙 II).

## 2. 에이전트 타입

| 에이전트 | 타입 | 파일 |
| --- | --- | --- |
| 오케스트레이터 | `OrchestratorRequest`(`request_type`에 `trend_report` 추가), `UncoveredQueryEvent` | `orchestrator/schemas.py`, `orchestrator/uncovered.py` |
| 트렌드 리포트 | `TrendReportRequest`, `Claim`, `Evidence`, `TrendCards`, `TrendCardsDraft`(LLM 출력), `BrokerView`, `TargetPriceTrend`, `VerificationSummary`, `TrendReportResult` | `agents/trend_report/schemas.py` |
| 인사이트보드 | `CompanyData`, `Badge`, `Comment`, `FeatureSummary`, `InsightBoardResult` | `agents/insight_board/schemas.py` (신규) |

- `Claim`·`Evidence`는 토론(`debate_renewal/schemas.py`)에도 있다. 계약 필드가 같으면 PR-1에서 `backend/contracts/evidence.py`로 옮겨 공용으로 쓴다. 다르면 유민과 맞춘 뒤 옮긴다(두 정의를 오래 두지 않음).

## 3. 저장소 (Supabase, 신규 마이그레이션)

### `agent_jobs`

| 컬럼 | 타입 | 규칙 |
| --- | --- | --- |
| `job_id` | text PK | `debate_<uuid hex>` |
| `user_id` | text not null | 세션 사용자 |
| `job_type` | text not null | `debate` |
| `mode` | text not null | `single` · `compare` |
| `tickers` | text[] not null | 1~2개, 6자리 문자열 |
| `query` | text not null | 재사용 판정 키에 포함 |
| `status` | text not null | `JobStatus` check 제약 |
| `precheck` | jsonb not null | `PrecheckResult` |
| `debate_result` · `simulation_result` | jsonb | 없으면 null |
| `error_code` | text | `interrupted` 등 |
| `created_at` · `updated_at` | timestamptz | |

- 인덱스: `(user_id, status)` — 동시 한도·재사용 조회.
- 재사용 키: `user_id`, 정렬한 `tickers`, `query`, `status in ('queued','running')`.

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

## 4. 상태 전이 (`JobStatus`)

```text
queued → running ─┬─ (compare) → debate_completed                         종료
                  └─ (single)  → simulation_pending ── 사용자 버튼 ──▶ simulation_running → completed
                                       │ 누르지 않으면 여기서 멈춤 (토론 결과 조회 가능)
running · simulation_running ── 실패 ──▶ failed
```

- 버튼: `POST /orchestrate/debate/{job_id}/simulate`(계약 #46). 비교 모드·이미 실행 중·완료면 409 `invalid_job_state`, 시뮬레이션 파라미터 없는 종목이면 200 rejected `no_data`(job은 `failed`로 바꾸지 않음).
- 토론 완료 이벤트와 job 조회 응답에 `simulation_ready`를 포함.

- `running` → `failed`: 토론 실패, 또는 앱 재시작 정리(`error_code=interrupted`).
- 상태가 바뀔 때마다 대응 이벤트를 `job_events`에 같은 트랜잭션으로 남긴다(`job_started`, `completed`, `failed`, `simulation_*`).
