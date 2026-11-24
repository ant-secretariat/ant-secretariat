# 0013. 시뮬레이션은 토론과 다른 job으로 실행하고, job 상태는 4종으로 줄인다

- 상태: 제안
- 결정일: 2026-11-24
- 결정자: 태은 (제안), 유민·수경 리뷰
- 의견을 준 사람: 수경 (동의, PR #68), 유민 (확인 필요)
- 출처: PR #68 리뷰, MVP Design Doc v1.5 4.1, API 계약 draft.5 `JobStatus`·`RunDebateInput`

## 배경

계약 draft.5는 토론과 시뮬레이션을 **job 하나의 상태 한 칸**으로 표현합니다.

```text
queued → running ─┬─ (비교) → debate_completed
                  └─ (단일) → simulation_pending ─ 버튼 → simulation_running → completed
```

이 구조에서 세 문제가 나왔습니다(PR #68).

1. 버튼을 누르지 않은 job이 `simulation_pending`에 계속 남아, "진행 중 job"을 셀 때 빼야 할지 규칙이 따로 필요했습니다. 빼지 않으면 버튼을 안 누른 사용자는 새 토론을 시작할 수 없습니다.
2. 시뮬레이션이 불가능한 종목(파라미터 수렴 실패·이력 부족)은 어디서 끝낼지 또 규칙이 필요했습니다.
3. 시뮬레이션이 실패하면 job 전체가 `failed`가 되어, 이미 끝난 토론까지 실패처럼 보입니다.

## 선택지

- **A. 계약대로 상태 한 칸 + 예외 규칙** — "진행 중"에서 `simulation_pending` 제외, 불가 종목은 `debate_completed`로 종료. 계약 변경 없음, 규칙이 늘어남
- **B. 상태 칸을 둘로 (`status` + `simulation_status`)** — 한 행에 두 상태. 문제 1·3은 풀리지만 큐가 한 행을 두 번 꺼내야 함
- **C. 시뮬레이션을 별도 job으로** — 토론 job과 시뮬레이션 job이 각자 상태를 가짐

## 결정

**C.** Design Doc 4.1도 큐 종류를 `debate`·`simulation` 두 가지(`job_type`)로 정해 두었습니다.

```text
토론 job       queued → running → completed (단일·비교 모두)  /  failed
                                     ▼ 사용자 버튼
시뮬레이션 job  queued → running → completed / failed      (debate_job_id = 토론 job)
```

- **상태는 job마다 4종**(`queued`·`running`·`completed`·`failed`). 계약 `JobStatus` 7종을 이렇게 줄입니다.
- **버튼:** `POST /orchestrate/debate/{job_id}/simulate`(경로는 그대로)가 시뮬레이션 job을 새로 만들어 그 job의 `job_started`를 돌려줍니다. 토론 job_id는 URL로 들어오고 시뮬레이션 job의 `debate_job_id`에 기록됩니다. 워커는 이 칸으로 토론 결과(`macro`·`risk` 아젠다)를 읽습니다.
- **기준일:** 시뮬레이션은 버튼을 누른 날이 아니라 **토론 job의 `data_as_of`** 로 실행합니다. 다음 날 눌러도 토론 근거와 시뮬레이션 숫자가 같은 날 기준이 됩니다. 봉투 `data_as_of`는 그 기준일의 `sim_params.as_of`입니다.
- **`simulation_ready`의 뜻:** "버튼을 눌렀는가"가 아니라 **"이 종목을 시뮬레이션할 수 있는가"**(`sim_params` 정상 여부, 11/23 기준 T1 100종목 중 95)입니다. 누르지 않아도 바뀌지 않습니다. 토론 완료 때 저장한 값은 화면 표시·지표용이고, `sim_params`가 매달 다시 계산되므로 **버튼을 누를 때 다시 판정**합니다.
- **버튼 요청 처리**

| 상황 | 응답 |
| --- | --- |
| 토론이 비교 모드이거나 아직 `completed`가 아님 | 409 `invalid_job_state` |
| 시뮬레이션 가능 기간이 지남 (토론 후 초기값 3~4일, #92) | 409 `invalid_job_state` ("새로 토론해 주세요") |
| 지금 시뮬레이션할 수 없는 종목 | 200 rejected `no_data` (토론 job은 그대로) |
| 같은 토론의 시뮬레이션 job이 진행 중이거나 끝남 | 그 job으로 `job_started` + `reused=true` |
| 그 외 | 시뮬레이션 job 생성 → `job_started` |

- `simulation_*` 이벤트는 시뮬레이션 job의 `job_events`에 기록합니다. FE는 새 job_id의 SSE를 구독합니다.

## 영향

- **쉬워지는 것:** 위 세 문제가 규칙 추가 없이 사라집니다. 토론의 종료 상태가 단일·비교 모두 `completed` 하나라 FE 처리가 같아집니다. 버튼은 기간 안이면 나중에 토론 내역에서 눌러도 됩니다.
- **감수하는 것:** 계약 변경(draft.6, `JobStatus` 4종·`simulate` 응답·이벤트 위치). FE가 시뮬레이션 job_id를 따로 구독해야 합니다.
- **다시 볼 조건:** 시뮬레이션 가능 기간은 `sim_params` 과거값 보관과 DB 용량 실측으로 #92에서 확정합니다.
- **바꿔야 하는 것:** 계약 `JobStatus`·`simulate` 설명·`JobEvent`(구현 계획 contracts C11), `agent_jobs.job_type`·`debate_job_id`·`data_as_of` 열(0012), 시뮬레이션 기획서(수경), 토론 패키지 상태 흐름 문서(유민).

## 참고

- 오케스트레이터 기획서 v2.3 6.3
- 0012 (테이블 큐), 0014 (사용자당 진행 중 job)
