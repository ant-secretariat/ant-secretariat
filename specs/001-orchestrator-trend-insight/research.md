# Research: 오케스트레이터·트렌드 리포트·인사이트보드 MVP

plan.md의 Technical Context에서 정해지지 않았던 항목을 정리한다. 각 항목은 결정·이유·검토한 대안 순서다. "확인 필요"는 담당자 확인 전까지 이 결정으로 진행하고, 바뀌면 이 문서와 기획서를 함께 고친다.

## R1. 공통 봉투와 사유 정책의 위치

- **결정:** `backend/contracts/envelope.py`에 계약 Envelope 모델과 `REASON_POLICY`, `make_reason()`을 둔다. `core/errors.py`(#60)의 Problem도 `REASON_POLICY`에서 HTTP 상태·`next_action`을 읽게 바꾼다.
- **이유:** 계약 OQ-1(`envelope.py`가 어느 브랜치에도 없음)을 해소하고, 사유 → 다음 행동 대응을 한 표로 강제한다. `backend/contracts/`는 토론 패키지 문서(`debate_renewal/CLAUDE.md`)에서 태은 소유로 정해진 위치다.
- **대안:** `orchestrator/envelope.py`(Notion 초안 위치) — 토론·인사이트보드도 쓰는 공용 타입이라 오케스트레이터 안에 두면 역방향 의존이 생긴다.

## R2. 작업 저장소

- **결정:** Supabase에 `agent_jobs`·`job_events`·`uncovered_query_log` 테이블을 새 마이그레이션으로 만든다. 접근은 데이터 함수와 같은 `crawling.db.postgres.connect()`(psycopg)를 쓴다.
- **이유:** ADR 0009의 SSE가 `job_events` 테이블 조회를 전제로 한다. 지금 `agent_jobs`는 SQLite `reports.db`에 있어 배포 환경에서 공유되지 않는다.
- **대안:** SQLite 유지 — 배포 인스턴스가 둘 이상이면 깨지고, 데이터 함수는 이미 Supabase다. 외부 큐(Redis 등) — MVP 규모에 비해 운영 비용이 크다.
- **범위 밖:** `users`·온보딩 테이블의 Supabase 이전은 별도 이슈로 둔다(시뮬레이션도 읽으므로 수경과 함께). 이 기능은 `user_id` 문자열만 저장한다.

## R3. 커버 종목 판정과 경로별 실행 조건 (#68 리뷰로 확정)

- **결정:** 커버 = 우선주가 아님 + `data_status.sources`에 적재된 소스가 1개 이상. 경로마다 필요한 소스는 선언형 표 `ROUTE_REQUIREMENTS`(`requires_any`, precheck의 `intent_data_sources.json`과 같은 형식)로 두고, 판정 함수 `check_coverage` 하나가 `unavailable`·`uncovered`·`no_data`·`ok` 네 상태를 돌려준다(오케스트레이터 기획서 5.3).
- **이유:** `companies` 2,867종목이 모두 티어를 가져서 "티어 있음"으로는 거의 전부 커버가 된다. 실제 적재는 T1 100종목뿐이다(수경, 11/23). 조건을 코드 분기 대신 표로 두면 경로를 추가할 때 판정 로직을 건드리지 않는다(Specification 패턴의 파라미터형).
- **대안:** (1) 티어로 판정 — 위 이유로 기각. (2) 에이전트마다 `resolve_company` 구현을 두기 — 데이터 함수가 소비자를 알게 되고, `data_status`는 이미 한 번의 조회로 모든 소스를 돌려줘 이득이 없다. (3) 컴포지트 Specification·라이브러리 — 지금 조건은 "하나라도 있음"뿐이라 과하다. 조합 조건이 생기면 평가 함수만 바꾼다.
- **`data_status` 실패:** `None`이거나 `error`가 있으면 503. "데이터 없음"으로 읽지 않는다(원칙 III).

## R4. 토론 job 실행 방식

- **결정:** API 프로세스 안 `asyncio` 백그라운드 작업(지금 방식 유지). 앱 시작 시 `queued`·`running` job을 `failed`(`error_code=interrupted`)로 정리하고 `failed` 이벤트를 남긴다.
- **이유:** MVP 데모는 단일 인스턴스다. 큐 도입은 범위·일정 대비 이득이 작다.
- **대안:** Supabase를 큐로 쓰는 별도 워커 — Post-MVP. `RunDebateInput` 계약은 그대로라 바꿀 때 호출부만 교체한다.

## R5. 목표주가 방향 임계값 — 확인 필요 (운영 DB)

- **결정:** 기획서 v2.0 4.2의 규칙(90일, 2/3, ±3%)으로 시작하고, 구현 PR에서 운영 DB 96종목 분포를 PR 본문에 붙여 확정한다(헌법 원칙 V).
- **대안:** 컨센서스 평균 변화만 보는 규칙 — 증권사 수가 바뀌면(새 증권사 진입) 평균이 움직여 방향이 왜곡된다.

## R6. 인증 (계약 OQ-8) — 팀 결정 필요

- **결정(제안):** 표준 `hmac`으로 서명한 httpOnly 쿠키 `session=<user_id>.<sig>`. `POST /users`가 발급, 의존성 `current_user_id()`가 검증. 이행 기간에는 쿠키가 없으면 바디 `user_id`를 받는다.
- **이유:** 계약이 쿠키 방식을 정했고(EventSource는 헤더를 못 보냄), 새 의존성 없이 구현된다.
- **대안:** JWT 라이브러리 — 세션 만료·회전 요구가 아직 없다. Supabase Auth — 로그인 기능 자체가 MVP 범위 밖이다.

## R7. 공통 텍스트 검사 위치

- **결정:** `backend/verification/text_rules.py`에 금지 표현·자리표시 규칙을 두고, 토론 L1은 여기서 import한다(유민 리뷰).
- **이유:** 같은 정책(투자 권유 금지)이 세 에이전트에 복사되면 한쪽만 바뀐다(DRY, #59). 인사이트보드·트렌드 리포트가 토론 패키지 내부를 import하는 역방향 의존도 피한다.
- **대안:** `agents.debate_renewal.validation.l1`을 직접 import — 다른 에이전트 내부 구현에 묶인다.

## R8. LLM 구조화 출력 — 구현 PR에서 확인

- **결정:** Upstage(OpenAI 호환)의 JSON 응답 모드로 받고 Pydantic으로 검증한다. 실패 시 1회 재요청, 그래도 실패하면 503.
- **이유:** 모델(`solar-mini` 등)마다 JSON 스키마 강제 지원 여부가 다르다. Pydantic 검증은 모델과 무관하게 동작한다.
- **확인:** 구현 PR에서 `response_format={"type": "json_schema", ...}` 지원 여부를 실제 호출로 확인하고, 지원하면 쓴다.

## R9. 계약 테스트

- **결정:** 테스트 전용 의존성 `pyyaml`·`jsonschema`를 추가해 응답 예시를 `openapi.yaml`의 컴포넌트 스키마로 검증한다(`tests/contract/`).
- **이유:** 헌법 원칙 II(계약 우선)를 사람 리뷰가 아니라 테스트로 확인한다. `test_enums.py`도 yaml이 없어 3개가 건너뛰어지고 있다.
- **대안:** FastAPI가 만든 OpenAPI와 비교 — 우리 계약은 손으로 쓴 원본이 기준이라 방향이 반대다.

## R10. SSE 구현

- **결정:** FastAPI `StreamingResponse` + async 제너레이터(1초 `asyncio.sleep` 조회, 15초 `: ping`). 새 의존성 없음.
- **대안:** `sse-starlette` — 기능은 충분하지만 이 정도 구현에 의존성을 늘릴 이유가 없다.

## R11. 날짜

- **결정:** 기준일은 `crawling.config.clock.today_kst()`. 모든 데이터 함수 호출에 `as_of`를 명시한다. 일부 데이터 함수가 기본값으로 `date.today()`를 쓰기 때문이다(#55).

## R12. 트렌드 리포트 지연

- **결정:** `run_trend_report`를 async로 바꾸고 `get_agent_context`·`get_disclosure_data`·90일 전 목표주가·`get_available_data_status`를 `asyncio.to_thread`로 병렬 호출한다. LLM은 1회(+재요청 1회, 보완 후 재생성 없음).
- **이유:** 지금은 검색 3종이 순차라 10초 목표의 대부분을 데이터 조회가 쓴다. `get_agent_context` 내부의 순차 검색은 수경 쪽 개선 대상으로 따로 요청한다.

## R14. SSE 조회 연결

- **결정:** 앱에 작은 연결 풀(`psycopg_pool`, 최대 5)을 두고 SSE는 1초 조회 때만 빌린다.
- **이유:** 데이터 함수의 `connect()`는 호출마다 새 연결을 만든다. 1초마다 새 연결은 비용이 크고, 스트림마다 연결을 붙잡으면 Supabase 무료 플랜의 동시 연결 한도에 걸린다(#68 리뷰).
- **대안:** `pg_notify` — ADR 0009에서 기각(트랜잭션 풀러에서 LISTEN 불가).

## R15. `append_event` 직렬화

- **결정:** 같은 트랜잭션에서 `pg_advisory_xact_lock(hashtext(job_id))` 후 `max(seq)+1` 삽입.
- **이유:** 비교 모드는 종목별 Bull·Bear가 병렬이라 같은 job에 이벤트가 동시에 들어온다(#68 리뷰).
- **대안:** 전역 자동 증가 `seq` — 잠금은 필요 없지만 커밋 순서가 뒤바뀌면 SSE 클라이언트가 앞 번호를 놓친다. asyncio Lock — 재시작·다중 워커에서 깨진다.

## R13. `mentioned_in_query`

- **결정:** `extract_company_mentions(query)`가 종목을 하나 이상 돌려주면, 그 `ticker` 집합과 확정 종목이 겹칠 때 true, 아니면 false. **빈 목록이면 `None`**을 넘겨 precheck가 공식명·종목코드로 직접 확인하게 한다.
- **이유:** 이 함수는 조회 실패와 "언급 없음"을 모두 빈 목록으로 돌려줘 구분할 수 없다. 빈 목록을 false로 바꾸면 조회 실패 때 precheck가 별칭 질문을 거절한다(헌법 원칙 III). `None`은 지금 precheck의 기본 동작이라 안전하다.
