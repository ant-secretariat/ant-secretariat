# 0012. 장시간 작업은 Postgres 테이블 큐와 워커 프로세스로 실행한다

- 상태: 채택
- 결정일: 2026-11-24
- 결정자: 태은
- 의견을 준 사람: 유민, 수경 (PR #68 리뷰)
- 출처: MVP Design Doc v1.5 4.1·5장, 오케스트레이터 기획서 6장, PR #68

## 배경

토론(수 분)과 시뮬레이션은 HTTP 요청 안에서 끝낼 수 없어 따로 실행해야 합니다. 지금 코드는 API 프로세스 안에서 `asyncio.create_task`로 돌려서, API를 재시작하거나 재배포하면 진행 중인 작업이 사라지고 아무도 모릅니다. Design Doc v1.5 4.1은 Postgres 테이블 큐를 정했지만 저장소에 기록이 없었고, 오케스트레이터 기획서 v2.0~2.1은 이를 놓쳐 `asyncio` 방식으로 적었습니다(v2.2에서 정정).

## 선택지

- **A. API 안 `asyncio` 백그라운드 (지금 코드)** — 추가 구현이 없음. 재시작·재배포 시 작업 유실, 워커를 늘릴 수 없음
- **B. Redis 큐 (RQ, Celery 등)** — 처리량이 높고 기능이 많음. Redis 서비스를 새로 운영해야 함
- **C. Postgres 큐 라이브러리 (PgQueuer, Procrastinate)** — 기능 충분. LISTEN에 기대는데 Supabase 트랜잭션 풀러에서 LISTEN이 안 되고, 학습 비용이 있음
- **D. Postgres 테이블 + 워커 프로세스 (`FOR UPDATE SKIP LOCKED`)** — 이미 쓰는 Supabase만으로 구현

## 결정

**D.** `agent_jobs` 테이블의 `status`가 큐 역할을 하고, API와 분리된 워커 프로세스가 꺼내 실행합니다. 두 프로세스는 DB로만 소통합니다.

### 동작

| 단계 | 누가 | 하는 일 |
| --- | --- | --- |
| 넣기 | API | `insert` (`status='queued'`). 이 insert가 곧 큐 등록 |
| 꺼내기 | 워커 | 한 트랜잭션에서 `select … where status='queued' order by created_at for update skip locked limit 1` → `update status='running', locked_by, heartbeat_at` → 커밋 |
| 실행 중 | 워커 | 15초마다 `heartbeat_at` 갱신 (상태는 그대로 `running`) |
| 끝내기 | 워커 | `update status='completed'`(또는 `failed`), 결과 저장 |
| 복구 | 워커 | 시작 시와 1분마다, `running`인데 `heartbeat_at`이 2분 넘게 멈춘 job → `failed` + `error_code=worker_lost`. **자동 재실행 안 함**(LLM 비용 중복 방지, FE가 "다시 시도") |
| 타임아웃 | 워커 | 토론 전체 5분, LLM 호출 1회 60초 → `failed` + `error_code=timeout` |

- **워커는 LLM이 아니라 우리 Python 프로세스**(`python -m orchestrator.worker`)입니다. LLM은 워커가 job을 실행하는 도중에 부르는 외부 API일 뿐 큐와 무관합니다.
- **잠금은 Postgres 행 잠금**입니다. `FOR UPDATE`는 고른 행을 다른 트랜잭션이 못 건드리게 하고, `SKIP LOCKED`는 이미 잠긴 행을 기다리지 않고 다음 행으로 넘어갑니다. 잠금은 꺼내는 트랜잭션(수 밀리초)에만 걸리고 커밋하면 풀립니다. 실행 중(수 분)의 소유권은 잠금이 아니라 `status='running'`·`locked_by`로 표시합니다. 실행 내내 잠금을 잡으면 DB 연결·트랜잭션을 수 분 열어 둬야 하고(무료 플랜 연결 수 제한), 워커가 죽었을 때 언제 풀릴지 불분명해집니다.
- **하트비트는 상태 확인이 아니라 생존 신호**입니다. 워커가 죽으면 그 job이 `running`으로 영원히 남아 사용자 한도(0014)까지 막히므로, 멈춘 하트비트로 "워커가 사라진 job"을 판단합니다.

### `SKIP LOCKED`가 필요한 경우

한 사용자의 동시 클릭이 아니라(그건 0014의 사용자 한도가 막음) **꺼내는 쪽이 여럿일 때**입니다. MVP는 워커 프로세스 1개지만 다음 두 경우에 꺼내기가 겹칩니다.

1. 워커 하나가 job을 동시에 3개까지 실행합니다(Design Doc 4.5). 슬롯마다 꺼내는 시점이 겹칠 수 있습니다.
2. 배포할 때 잠깐 옛 워커와 새 워커가 같이 떠 있습니다.

```text
queued: D1(u1, 10:00:01), D2(u2, 10:00:02)

        슬롯/워커 A                         슬롯/워커 B
t1  D1 잠금 (가장 오래된 queued)
t2                                     D1은 잠김 → 건너뜀, D2 잠금
t3  D1 → running, 커밋 (잠금 풀림)       D2 → running, 커밋
t4  D1 실행                             D2 실행
```

- B는 D2를 "미리" 잠그는 게 아니라, 자기가 지금 실행할 job으로 D2를 가져가는 것입니다. queued가 D1뿐이면 B는 아무것도 못 가져가고 1~2초 뒤 다시 조회합니다.
- A가 이미 커밋한 뒤라면 D1은 `running`이라 조건(`status='queued'`)에서 빠집니다. `SKIP LOCKED`가 막는 건 "A가 골랐지만 아직 커밋하지 않은" 그 사이입니다.
- 잠금이 없으면 두 쪽이 D1을 동시에 실행해 LLM 비용이 두 배가 되고 결과가 두 번 저장됩니다.

### 워커 내부: dispatcher 하나 + `Semaphore(3)`

워커는 job을 동시에 3개까지 실행합니다(Design Doc 4.5). 꺼내는 주체를 두 가지로 검토했습니다. 두 방식 모두 꺼내기 SQL은 같고(`SKIP LOCKED`), 차이는 **누가** 꺼내느냐입니다.

| | 슬롯 3개가 각자 꺼내기 | **dispatcher 하나가 꺼내고 세마포어로 할당 (선택)** |
| --- | --- | --- |
| 같은 프로세스 안 꺼내기 겹침 | 있음 (`SKIP LOCKED`가 해결) | 없음 |
| 큐가 비었을 때 DB 조회 | 1.5초마다 슬롯 수만큼 | 1.5초마다 1번 |
| 하트비트·종료 처리·실행 수 파악 | 슬롯마다 따로 | 한 곳에서 (하트비트 일괄 갱신, 꺼내기 중단 후 실행 중 job 대기) |
| 주의할 점 | 적음 | dispatcher가 예외로 멈추지 않게 반복마다 예외 처리, `finally`에서 자리 반납 |

- 정확성은 두 방식 모두 같으므로 DB 조회 수와 운영 편의로 골랐습니다(무료 플랜 연결·부하가 빠듯함).
- `SKIP LOCKED`는 남겨 둡니다. 배포 순간 옛 워커와 새 워커가 겹칠 수 있습니다.
- 워커는 이벤트 루프(스레드 1개) 위에서 돕니다. 토론 job은 시간 대부분이 LLM 응답 대기라 job 3개가 스레드 하나를 `await` 지점마다 번갈아 씁니다. 계산이 많은 작업(시뮬레이션 모델)은 `to_thread`로 별도 스레드에서 실행합니다.
- 큐 SQL(꺼내기·하트비트·이벤트 기록)도 데이터 함수와 같은 동기 psycopg를 `to_thread`로 실행합니다. 작업량이 적어(각 수 밀리초) 비동기 psycopg와 성능 차이가 없고, DB 접근 방식이 하나로 통일되며, 윈도우 개발 환경의 이벤트 루프 설정이 필요 없습니다. 비동기는 API의 SSE 동시 연결이 많아질 때 SSE 조회만 다시 검토합니다.

### Redis가 아닌 이유

| 기준 | 테이블 큐 (D) | Redis 큐 (B) |
| --- | --- | --- |
| 인프라 | 이미 쓰는 Supabase | Redis 서비스 추가(호스팅·키·모니터링·비용) |
| job 생성과 큐 등록 | insert 한 번 | DB 행 + Redis 등록 두 번 → 한쪽만 성공하면 불일치 |
| 사용자당 진행 중 1개 | 부분 유니크 인덱스로 DB가 강제 (0014) | 직접 구현 |
| 결과·진행 이벤트·내역 | 같은 DB라 SSE(0009)·토론 내역·완료율 SQL과 바로 연결 | 큐 상태와 DB 상태가 따로 놂 |
| 재시작 | 기본으로 디스크 저장 | 영속 설정 필요 |
| 처리량 | 우리 필요량(시간당 수십 건)에 충분 | 더 빠르지만 필요 없음 |

Design Doc의 MVP 원칙("새 라이브러리·인프라 최소화")과 5장의 Celery+Redis 기각("인프라 추가")과 같습니다. 같은 원리(`FOR UPDATE SKIP LOCKED`)로 동작하는 큐 라이브러리가 실무에서 쓰입니다: pg-boss(Node.js), PgQueuer(Python, 선택지 C), River(Go).

실무 글들이 강조하는 주의점과 이 결정의 대응입니다.

| 주의점 | 대응 |
| --- | --- |
| `FOR UPDATE`만 쓰면 워커가 한 행에서 줄을 섬 | `SKIP LOCKED` |
| 외부 호출 내내 잠금을 잡으면 다른 워커가 멈춤 | 꺼내기만 짧은 트랜잭션으로 커밋, LLM 호출은 그 뒤 |
| 긴 job은 갱신하는 타임스탬프(임대)로 관리해 죽은 워커의 job 회수 | `heartbeat_at` 15초, 2분 끊기면 `worker_lost` |
| 웹 요청과 job 처리의 연결 풀을 섞지 않기 | API(SSE)는 작은 풀, 워커는 세션 모드 연결 |
| 행을 자주 바꾸고 지우면 테이블이 부풀고 vacuum 부담 | 우리 규모(시간당 수십 건)에서는 작음, 끝난 job 정리 규칙(#92) |
| 폴링 대신 LISTEN/NOTIFY로 깨우기 | Supabase 트랜잭션 풀러에서 LISTEN 불가 → 큐가 비었을 때만 1.5초 폴링 (0009와 같은 이유) |

## 영향

- **쉬워지는 것:** API를 재배포해도 토론이 계속되고, 워커가 죽어도 2분 안에 정리됩니다. 큐 상태·결과·이벤트가 한 DB에 있어 조회·집계가 SQL 하나입니다.
- **감수하는 것:**
  - 일이 없을 때도 워커가 1~2초마다 조회합니다(워커 몇 개 수준에서는 부담 없음).
  - 끝난 job이 쌓이면 정리가 필요합니다(보관 기간은 #92).
  - 자동 재실행이 없어 일시적 실패도 사용자가 다시 시작해야 합니다.
- **다시 볼 조건:** 시간당 수천 건 이상, 또는 재시도·예약 실행 같은 큐 기능이 많이 필요해지면 C(PgQueuer) 또는 B를 검토합니다.
- **바꿔야 하는 것:** 마이그레이션 `agent_jobs`(하트비트 열 포함)·`job_events`, `backend/orchestrator/worker.py`, `functions/agent_jobs.py`의 SQLite 제거(구현 계획 PR-2).

## 참고

- 오케스트레이터 기획서 6.1(스키마)·6.2(실행)
- 0009 (SSE 전달), 0013 (시뮬레이션 별도 job), 0014 (사용자당 진행 중 job)
- PostgreSQL `SELECT … FOR UPDATE SKIP LOCKED` (Locking Clause)
- [pg-boss](https://github.com/timgit/pg-boss), [PgQueuer — SKIP LOCKED](https://janbjorge.github.io/pgqueuer/reference/skip-locked/)
- [Encore — Postgres job queue with SKIP LOCKED](https://encore.dev/articles/postgres-job-queue-skip-locked), [Neon — queue system](https://neon.com/guides/queue-system)
- [Microsoft — Potential consequences of using Postgres as a job queue](https://techcommunity.microsoft.com/blog/adforpostgresql/potential-consequences-of-using-postgres-as-a-job-queue/4514332)
