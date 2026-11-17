# 0009. 진행 이벤트는 `job_events`를 1초마다 읽어 SSE로 보내고, 단위는 단계와 주장이다

- 상태: 제안
- 결정일: 2026-11-17
- 결정자: 태은 (제안), 유민·수경 리뷰
- 출처: 멀티에이전트 설계 최종 확정 1장·3장, Design Doc 4.2, 토론 기획서 v3.0 D8·미결 Q2(PR #20)

## 배경

토론 진행 상황을 FE에 보내는 방식이 세 문서에서 달랐습니다.

| 문서 | 서버 안 전달 | 이벤트 단위 |
| --- | --- | --- |
| 멀티에이전트 설계 최종 확정 | `job_events` + `pg_notify` | LangGraph `stream_mode="messages"` 중계 |
| Design Doc 4.2, API 계약 | `job_events`를 1초마다 조회 | 단계 단위 (`job_started`, `bull_completed` 등) |
| 토론 기획서 v3.0 | `job_events` + `pg_notify` | 노드·주장 단위 (`node_started`, `claim_completed` 등) |

API와 워커는 다른 프로세스이고, DB는 Supabase 풀러로 접속합니다.

## 선택지

**서버 안 전달**

- **A. `pg_notify` + LISTEN** — 지연이 가장 짧음. 하지만 Supabase 트랜잭션 모드 풀러에서는 LISTEN이 동작하지 않아 API가 직접 연결이나 세션 모드 연결을 따로 유지해야 함. 알림을 놓치면 테이블을 다시 읽어야 하므로 조회 코드도 결국 필요함
- **B. `job_events`를 1초마다 조회** — 진실의 원천이 테이블 하나. 재시작·재접속·다중 워커가 같은 코드로 해결됨. 최대 1초 지연
- **C. Supabase Realtime** — FE가 DB에 직접 붙어야 해서 RLS 정책과 계약이 API 밖으로 나감

**이벤트 단위**

- **토큰 단위** — 토론 1건에 수천 행. 출력이 strict JSON이라 토큰 조각은 그릴 수도 없음
- **일반 노드 이름** (`node_started`/`node_completed` + 노드명) — 이벤트 종류는 적지만, FE가 노드명을 다시 해석해야 함
- **단계 이름 + 주장 이벤트** — 단계 이벤트가 PRD 6.4 문구와 1:1, 주장은 카드 단위로 채움

## 결정

**서버 안 전달은 B(1초 조회)입니다.** MVP에서는 `pg_notify`를 쓰지 않습니다.

- `GET /jobs/{job_id}/events`가 `seq > 마지막 seq`인 행을 1초마다 읽어 보냅니다. 각 이벤트의 `id`는 `seq`입니다.
- 재접속하면 브라우저가 보내는 `Last-Event-ID` 다음부터 보냅니다. 새로고침해도 빠지는 이벤트가 없습니다.
- 새 이벤트가 없으면 15초마다 `: ping`을 보내고, `completed`·`failed` 뒤에는 연결을 닫습니다.
- 본인 job만 열 수 있습니다. 인증은 세션 쿠키입니다(`EventSource`는 헤더를 못 보냄).
- SSE가 실패하면 FE는 `GET /debate/jobs/{job_id}` 폴링으로 바꿉니다.

**이벤트 단위는 단계 이름 + 주장 이벤트입니다.**

- 단계 이벤트는 API 계약의 `JobEvent.type`을 그대로 씁니다: `job_started`, `data_collected`, `bull_completed`, `round2_started`, `bear_completed`, `verifying`, `judge_completed`, `completed`, `failed`, `simulation_*`.
- 토론 기획서 v3.0의 제안을 받아 **`claim_completed`를 추가**합니다. payload는 역할(`bull`·`bear`), `agenda_id`, 주장 요약입니다. FE는 이 이벤트로 주장 카드를 하나씩 채웁니다.
- 2종목 비교(ADR 0007)에서는 종목별 이벤트의 payload에 `ticker`를 넣어 FE가 종목별로 나눠 그립니다. job 전체 이벤트는 `ticker`가 없습니다.
- LangGraph `stream_mode="messages"`는 중계하지 않습니다.
- 한 job의 `seq`는 그 job을 가진 워커 한 곳에서만 매깁니다. 비교 모드처럼 한 job 안에서 병렬로 실행해도 `seq`를 매기는 곳은 하나로 둡니다.

**`pg_notify`를 다시 볼 조건** (하나라도 해당하면)

- 이벤트가 화면에 보이기까지의 지연이 사용성 테스트에서 문제로 나올 때
- 동시 SSE 연결이 많아져 초당 조회 수가 DB에 부담이 될 때 (기준: 연결 50개 이상)

이때도 `pg_notify`는 "새 이벤트가 있다"는 신호로만 쓰고, 내용은 계속 테이블에서 읽습니다.

## 영향

- **쉬워지는 것:** 새 의존성이 없습니다(FastAPI `StreamingResponse`). 풀러 모드와 상관없이 동작합니다. 데모 모드(Design Doc 4.6)는 저장한 `job_events`를 같은 엔드포인트로 재생하면 됩니다.
- **감수하는 것:** 이벤트가 최대 1초 늦게 보입니다. 연결마다 초당 PK 조회 1번이 생깁니다.
- **바꿔야 하는 문서·계약:**
  - `docs/api/openapi.yaml`: `JobEvent.type`에 `claim_completed` 추가, payload에 선택 필드 `ticker`
  - 멀티에이전트 설계 최종 확정 1장 6번·3장의 `pg_notify`·`stream_mode="messages"` 표기는 이 ADR이 대체합니다.
  - 토론 기획서 v3.0 D8의 이벤트 이름을 계약 이름으로 맞춥니다(미결 Q2 해소).

## 참고

- Design Doc 4.2 "진행 이벤트와 SSE", 4.3 "DB 연결"
- [Supabase — Connection pooler modes](https://supabase.com/docs/guides/database/connecting-to-postgres)
- [MDN — Server-sent events, `Last-Event-ID`](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
