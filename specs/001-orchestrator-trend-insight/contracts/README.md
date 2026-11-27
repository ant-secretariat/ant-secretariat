# 계약 변경 목록 (PR-0, draft.5 → draft.6)

계약 원본은 [`docs/api/openapi.yaml`](../../../docs/api/openapi.yaml) 하나다. 이 폴더에 스키마를 복사하지 않는다. 아래는 이 기능이 계약에 넣어야 할 변경 목록이고, PR-0에서 반영한다(헌법 원칙 II: 계약을 쓰는 쪽 담당자 리뷰).

| # | 대상 | 변경 | 이유 | 리뷰 |
| --- | --- | --- | --- | --- |
| C1 | `info.description` | 사유 정책표(`REASON_POLICY`: 코드 → 채널·HTTP·next_action·payload) 추가, OQ-1 닫기 | 표가 계약 어디에도 없음 | 전원 |
| C2 | `EntityResolution.companies` | `maxItems: 2` → `3`, 설명에 "토론은 `max_companies=2`" | 인사이트보드는 3종목 | 유민·수경 |
| C3 | `BrokerView` (신규) | `broker`, `opinion`, `target_price`, `published_at`, `view: Claim` | `broker_differences` 항목이 미정의 | — |
| C4 | `VerificationSummary` (신규) | `checked`, `retracted`, `gap_filled`, `failed_checks` | `TrendReportResult.verification`이 열린 객체 | 유민 (토론도 같은 집계를 쓸지) |
| C5 | `CompanyData.ticker` | 매크로 항목은 `"macro"` | 매크로는 종목이 없음 | — |
| C6 | `TargetPriceTrend` | `direction` 계산 규칙(개정 비율, #82 경계값)을 설명에, 상향·하향·유지 개정 수 필드 추가 | 코드 계산 규칙 공개, 화면에 숫자 표시 | 수경 |
| C7 | `OrchestratorRequest`·`run_orchestrator_request` | MVP는 탭별 엔드포인트가 경로를 정하고 라우팅하지 않음(ADR 0015). `request_type`·`decide_route`·`chat`은 Post-MVP로 표시 | 범위 명확화 | — |
| C8 | `job_not_found` · `invalid_job_state` | "제안" 표시 제거 (OQ-2 닫기) | 구현에서 사용 | 전원 |
| C9 | `suggest_alternatives(ticker, n=3)` (신규 데이터 함수) | 중분류 → 대분류 → 전체 시총순, `alternatives` 3개 | 거절 대안 선정 (#68 리뷰) | 수경 |
| C10 ✅ #99 | `JobEvent` 토론 완료 payload · job 조회 응답 | `simulation_ready` 추가 | 버튼 미리 끄기 (#68 리뷰) | 수경 |
| C11 ✅ #99 | `JobStatus`, `simulate` | 7종 → `queued`·`running`·`completed`·`failed` 4종, 시뮬레이션은 별도 job(`job_type`·`debate_job_id`, 기준일은 토론 `data_as_of`, ADR 0013), `simulate`는 시뮬레이션 job의 `job_started`를 돌려줌, `simulation_*` 이벤트는 시뮬레이션 job에 기록, `run_simulation(ticker, user_id, debate_job_id, as_of)` | 상태 한 칸 공유 문제 (오케스트레이터 기획서 v2.2 6.3) | 유민·수경 |
| C12 | `RunDebateInput`·`run_debate` note | `run_debate`는 결과만 돌려주고 `job_events`·상태는 워커가 기록. `emit`·`fetch_evidence`·`profile` 주입, `CompanyMeta.data_tier` | #68 유민 제안 (#76) | 유민 |

- 계약 테스트(`backend/tests/contract/`)를 같은 PR에 넣어, 이후 PR의 응답이 이 스키마로 검증되게 한다.
- `/agents/trend-report`는 이미 `deprecated`다. 삭제는 PR-12.
