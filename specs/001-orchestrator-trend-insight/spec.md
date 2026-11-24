# Feature Specification: 오케스트레이터·트렌드 리포트·인사이트보드 MVP 리빌드

**Feature Branch**: `docs/001-orchestrator-trend-insight`

**Created**: 2026-11-23

**Status**: Draft

**Input**: 오케스트레이터(C)·트렌드 리포트(D)·인사이트보드(E)를 각 기획서 v2.0에 맞춰 구현한다.

**기준 문서** (이 spec은 요약이고, 세부 규칙은 아래 기획서가 원본이다)

- [오케스트레이터 기획서 v2.0](../../docs/orchestrator/orchestrator-spec.md)
- [트렌드 리포트 기획서 v2.0](../../docs/trend-report/trend-report-spec.md)
- [인사이트보드 기획서 v2.0](../../docs/insight-board/insight-board-spec.md)
- 계약 [`docs/api/openapi.yaml`](../../docs/api/openapi.yaml) `1.0.0-draft.5`, ADR 0005·0006·0007·0009·0010

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 종목을 골라 토론을 시작하면 바로 진행 상황을 본다 (Priority: P1)

사용자가 종목 1~2개와 질문으로 "토론 시작"을 누르면, 토론할 수 없는 요청은 job 없이 이유와 다음 행동을 바로 받고, 가능한 요청은 job이 만들어져 진행 상황이 실시간으로 보인다.

**Why this priority**: 토론은 핵심 기능이고 다른 담당(토론·시뮬레이션)의 진입점이다. precheck·job·SSE가 없으면 유민·수경의 작업이 연결되지 않는다.

**Independent Test**: `POST /orchestrate/debate` → `job_started` → `GET /jobs/{id}/events`에서 이벤트 수신. 범위 밖 질문은 `rejected` + `choose_supported_topic`.

**Acceptance Scenarios**:

1. **Given** 커버 종목 1개와 범위 안 질문, **When** 토론 시작, **Then** precheck 통과 후 job이 생기고 `job_started {job_id, reused:false}`를 1초 안에 받는다.
2. **Given** 같은 사용자·종목·질문의 job이 진행 중, **When** 다시 시작, **Then** 새 job 없이 `reused:true`로 같은 job을 받는다.
3. **Given** 종목 3개, **When** 토론 시작, **Then** job 없이 `rejected too_many_companies` + `select_companies`.
4. **Given** 범위 밖 질문, **When** 토론 시작, **Then** job 없이 `rejected out_of_scope_topic` + `choose_supported_topic`, 미커버 로그 1건.
5. **Given** 시작된 job, **When** 새로고침 후 `Last-Event-ID`로 재접속, **Then** 그 다음 `seq`부터 이벤트를 받고 종료 이벤트 뒤 연결이 닫힌다.

---

### User Story 2 - 트렌드 리포트의 모든 문장은 근거로 이어진다 (Priority: P2)

사용자가 종목 하나의 트렌드 리포트를 열면 카드 6종을 10초 안에 받고, 모든 문장에서 근거 문서로 이동할 수 있다. 근거가 없는 문장은 보이지 않는다.

**Why this priority**: 서비스 신뢰성의 기준(헌법 원칙 IV)이고 FN-TR-01·02의 인수 조건이다.

**Independent Test**: 근거가 있는 종목·없는 종목·문서가 적은 종목(`news_only` 등) 각각으로 `POST /orchestrate/trend-report`를 호출해 `status`·카드 구성·인용을 확인한다.

**Acceptance Scenarios**:

1. **Given** 리포트가 있는 종목, **When** 트렌드 리포트 요청, **Then** `ok`, 모든 Claim의 `evidence_ids`가 `evidence`에 존재, 목표주가 평균은 `get_target_price_data.consensus`와 같다.
2. **Given** LLM이 근거 없는 문장을 쓴 경우, **When** 검증, **Then** 보완(S1~S3) 후에도 근거가 없으면 그 문장은 철회되고 `verification.retracted`에 집계된다.
3. **Given** 요약·리스크가 모두 철회된 경우, **Then** `status`는 `ok`가 아니다.
4. **Given** `macro_only` 종목, **Then** `rejected no_data` + `choose_alternative_company`.

---

### User Story 3 - 인사이트보드는 한 종목이 실패해도 나머지를 보여 준다 (Priority: P3)

사용자가 종목 1~3개와 기능(주가·매크로·공시)을 고르면 데이터·배지·코멘트를 받는다. 한 종목 조회가 실패해도 나머지는 보이고, 코멘트의 숫자는 데이터와 일치한다.

**Why this priority**: 이미 동작하는 기능의 정확성·형식 개선이라 P1·P2보다 뒤다.

**Independent Test**: 한 종목의 데이터 함수가 `error`를 돌려주도록 만든 뒤 요청해 `partial`과 나머지 종목 노출을 확인한다.

**Acceptance Scenarios**:

1. **Given** 3종목 중 1종목 조회 실패, **Then** `partial` + `retry_failed_parts [ticker]`, 나머지 2종목은 `ok`.
2. **Given** 코멘트에 요약에 없는 숫자, **Then** `comment.text=""`, `verified=false`, 요청은 성공.
3. **Given** 변동성이 시장 기준 이상인 종목, **Then** `volatility_high` 배지.

### Edge Cases

- 종목 조회 DB 실패 → 503 Problem(없는 회사로 보이지 않게).
- `ambiguous` 종목명("삼성") → 버튼 경로는 `rejected company_not_found` (FE 자동완성이 후보 제공).
- 워커 프로세스가 죽어 `running` job의 하트비트가 2분 넘게 끊김 → `failed` + `error_code=worker_lost`, 이벤트 `failed` 기록. 자동 재실행 없음.
- 토론이 끝난 뒤 시뮬레이션 버튼을 누르지 않음 → 토론 job은 `completed`, 새 토론 시작 가능.
- 트렌드 리포트 LLM JSON 파싱 2회 실패 → 503.
- 모든 인사이트보드 종목 실패 → 503.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 모든 진입점(`/orchestrate/insight-board`, `/trend-report`, `/debate`)은 공통 봉투를 돌려주고, 거절·부분 결과는 HTTP 200 `status`로, 인프라 오류는 Problem으로 구분해야 한다.
- **FR-002**: 모든 사유는 `REASON_POLICY` 표의 다음 행동과 payload를 가져야 한다.
- **FR-003**: 관문1은 종목 입력을 `EntityResolution`으로 확정하고, 조회 실패를 "없는 종목"과 구분해야 한다.
- **FR-004**: 토론 job은 precheck를 통과한 요청만 만들어야 하고, precheck에는 `mentioned_in_query`를 넘겨야 한다.
- **FR-005**: 같은 사용자·종목·질문의 진행 중 job은 재사용하고, 사용자당 동시 job 한도를 넘으면 409로 알려야 한다. 끝난 job은 한도에 세지 않는다.
- **FR-013**: 에이전트의 모든 데이터 조회는 도구 레지스트리 `invoke`를 거치고, 조회 실패를 `ToolResult.error`로 구분해야 한다.
- **FR-014**: 요청·job마다 Langfuse trace 1개를 남기고 응답 `meta.trace_id`와 같은 값을 써야 한다(설정이 없으면 보내지 않음).
- **FR-015**: 워커가 죽으면 2분 안에 job을 `failed(worker_lost)`로 정리해야 한다.
- **FR-006**: job 진행 이벤트는 `job_events`에 `seq` 순서로 쌓이고 SSE로 재전송 가능해야 한다.
- **FR-007**: 트렌드 리포트의 노출 주장은 모두 L1 인용 검사를 통과해야 하고, 숫자·목표주가 방향은 코드가 계산해야 한다.
- **FR-008**: 트렌드 리포트는 `data_tier`별 카드 정책을 따라야 한다.
- **FR-009**: 인사이트보드는 종목별 실패를 격리하고, 배지는 구조화(`Badge`), 코멘트는 검증 실패 시 빈 문자열이어야 한다.
- **FR-010**: 모든 데이터 조회는 `as_of`(KST 기준일)를 명시해 미래 정보를 쓰지 않아야 한다.
- **FR-011**: 거절된 질의는 `uncovered_query_log`에 가린 문장과 사용자 해시로 남아야 한다.
- **FR-012**: `user_id`는 세션 쿠키에서 주입하고, 이행 기간에는 바디 값을 허용한다.

### Key Entities

- **Envelope / Reason / ResponseMeta**: 공통 응답. 계약 스키마 그대로.
- **EntityResolution / CompanyContext**: 관문1 결과.
- **AgentJob / JobEvent**: 토론 작업과 진행 이벤트 (Supabase).
- **Claim / Evidence / TrendCards / BrokerView / VerificationSummary**: 트렌드 리포트.
- **CompanyData / Badge / Comment / FeatureSummary**: 인사이트보드.
- **UncoveredQueryEvent**: 미커버 로그.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 세 엔드포인트의 응답이 `openapi.yaml` 스키마 검증을 100% 통과한다 (계약 테스트).
- **SC-002**: 토론 요청 → `job_started` p95 ≤ 1초, 거절은 job 0건.
- **SC-003**: 트렌드 리포트 p95 ≤ 10초, 노출 주장의 근거 연결률 100%, 숫자 불일치 0건.
- **SC-004**: 인사이트보드 부분 실패 시 성공 종목 노출 100%.
- **SC-005**: 관문1 종목 입력셋 기대 status 일치율 ≥ 98%.

## Assumptions

- 자유 질의(채팅)·플래너·레지스트리의 LLM 도구 정의(`to_llm_tools`)·근거 부족 루프 S4~S5는 Post-MVP다(계약 11/5 결정). **도구 레지스트리와 Langfuse는 MVP다**(Design Doc v1.5, 토론 기획서 v3.0).
- `run_debate`·`precheck`는 유민, 데이터 함수·`get_agent_context`(#53)는 수경이 제공한다. 이 기능은 그 인터페이스를 호출만 한다.
- job 실행은 API와 분리된 워커 프로세스가 `FOR UPDATE SKIP LOCKED`로 꺼내는 Postgres 큐다(Design Doc 4.1). 외부 큐 인프라는 쓰지 않는다.
- 토론과 시뮬레이션은 서로 다른 job(`job_type`)이다(오케스트레이터 기획서 v2.2 6.3).
- 인증 방식(OQ-8)은 HMAC 서명 쿠키로 제안하고 팀 확정 전까지 바디 `user_id`를 병행 허용한다.
