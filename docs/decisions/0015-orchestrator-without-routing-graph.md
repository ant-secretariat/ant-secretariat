# 0015. MVP 오케스트레이터는 라우팅 그래프 없이 공통 관문과 응답 조립만 한다

- 상태: 채택
- 결정일: 2026-11-24
- 결정자: 태은
- 출처: 오케스트레이터 기획서 1·3장, FE 라우트(`frontend/src/App.tsx`), API 계약 draft.5(`/orchestrate/chat` Post-MVP), MVP Design Doc v1.5 2.2

## 배경

### 라우팅을 다시 보게 된 계기

지금 오케스트레이터는 LangGraph `StateGraph`로 `route → (insight_board | debate) → END`를 구성하고(`backend/orchestrator/graph.py`), 라우팅 함수 `decide_route()`가 요청의 `request_type`을 그대로 돌려준다(`router.py`). 기획서를 정리하면서 "이 라우팅이 실제로 무엇을 결정하는가"를 확인했다.

- **FE는 탭이 기능별로 나뉘어 있다.** `/insight`(인사이트보드), `/trend-report`(트렌드 리포트), `/debate`(토론) 탭이 각각 다른 엔드포인트를 부른다.

  ```text
  인사이트 탭  → POST /orchestrate/insight-board
  트렌드 탭    → POST /orchestrate/trend-report
  토론 탭      → POST /orchestrate/debate
  ```

- **어떤 에이전트로 보낼지는 URL에서 이미 정해진다.** `decide_route()`는 엔드포인트가 정한 값을 한 번 더 확인할 뿐이고, 그 한 줄을 위해 그래프 프레임워크를 두고 있었다.

### 라우팅이 원래 필요했던 곳: 자유 질의

라우팅이 실제로 판단을 해야 하는 건 **자유 질의**다. "삼성전자 요즘 어때?" 같은 문장 하나만 보고 트렌드 리포트·토론·시세 중 무엇을 보여 줄지, 어떤 종목인지를 시스템이 정해야 한다. 처음 설계(Notion 아키텍처 초안, 9/30 "1차 릴리스 포함")에서 라우팅과 플래너(`make_plan` → `validate_plan` → `execute_plan`)가 이 경로를 위해 있었다. 이후 11/5 결정으로 자유 질의는 Post-MVP가 되었다(Design Doc v1.1, API 계약 `/orchestrate/chat` `x-release: post-mvp`, Design Doc v1.5 2.2 비목표).

### 혼동했던 점: 토론 탭의 "직접 물어보기"는 자유 질의가 아니다

토론 탭에는 "직접 물어보기 (선택)" 입력칸이 있어 자유 질의가 MVP에 있다고 착각하기 쉬웠다. 하지만 이 입력은 성격이 다르다.

| | 토론 탭 "직접 물어보기" (MVP) | 자유 질의 (Post-MVP) |
| --- | --- | --- |
| 무엇을 할지 | 사용자가 이미 **토론**을 고름 | 문장을 보고 **시스템이 판단** |
| 어떤 종목인지 | 사용자가 칩으로 이미 **고름** | 문장에서 **시스템이 추출**, 애매하면 되묻기 |
| 입력이 가는 곳 | `POST /orchestrate/debate`의 `query` (비우면 기본 질문) | `POST /orchestrate/chat`의 `message` |
| 처리 | precheck가 범위 판정·아젠다 선택 (룰) | 종목 추출 → 플래너(LLM) → 계획 검증 → 실행 |
| 라우팅·플래너 | 필요 없음 | 필요함 |

즉 MVP의 모든 입력은 **탭(기능)과 종목이 먼저 정해진 상태**로 들어오므로, 무엇을 실행할지 판단하는 라우팅이 필요 없다.

### 그래도 오케스트레이터가 필요한 이유

라우팅은 필요 없지만, 세 탭이 공통으로 거쳐야 하는 일은 남는다. 탭마다 따로 구현하면 중복되고 서로 어긋난다.

| 하는 일 | 공통 여부 |
| --- | --- |
| 관문1: 종목 확정 + 경로별 실행 조건 판정 | 세 탭 공통 |
| 거절할 때 사유·다음 행동·대안 종목 채우기 (공통 봉투) | 세 탭 공통 |
| 세션 사용자 확인, 하루 한도, `trace_id` | 세 탭 공통 |
| 미커버 질의 로그 | 세 탭 공통 |
| precheck → job 생성·재사용·동시 한도 → 워커 | 토론만 |

## 선택지

- **A. LangGraph 라우팅 그래프 유지** — 지금 코드 그대로. 판단하지 않는 노드 하나를 위해 그래프·상태 타입·컴파일 단계를 유지
- **B. 그래프를 걷어 내고, 엔드포인트가 공통 관문 함수와 해당 에이전트를 바로 호출** — 흐름이 엔드포인트 하나에 다 보임
- **C. 그래프를 키워 관문1·precheck·job 생성까지 노드로** — 그래프가 실제 일을 하게 되지만, 분기 없는 순차 흐름이라 함수 호출과 차이가 없고 디버깅·테스트가 한 단계 멀어짐

## 결정

**B.** MVP 오케스트레이터는 "라우터"가 아니라 **공통 관문 + 응답 조립 모듈**이다.

```python
# api/orchestrator.py (MVP 모양)
@router.post("/orchestrate/trend-report")
async def trend_report(body: TrendReportBody, user_id: str = Depends(current_user_id)):
    gate = await resolve_and_check([body.company], route=("trend_report", None))   # 관문1 (공통)
    if gate.rejected:
        return gate.envelope                                                       # 거절 봉투 (공통)
    result = await run_trend_report(gate.companies[0], body)                       # 에이전트 직접 호출
    return ok_or_partial(result)                                                   # 응답 조립 (공통)
```

- 토론 엔드포인트는 관문1 뒤에 precheck → job 생성을 이어서 호출한다.
- **라우팅과 플래너는 자유 질의를 만들 때 다시 도입한다.** 그때 판단이 생기므로 그래프(LangGraph 등)가 필요한지 그 시점에 정한다.
- 이 결정은 멀티에이전트 설계 최종 확정·Design Doc의 "오케스트레이터 = LangGraph" 표기와 다르다. 헌법 우선순위상 ADR이 설계 문서보다 위라 이 ADR이 대체한다.

## 영향

- **쉬워지는 것:** 엔드포인트 하나만 읽으면 요청이 어떻게 처리되는지 보인다. 관문1·봉투가 함수라서 단위 테스트가 쉽다. 오케스트레이터 레이어에서 프레임워크 의존이 줄어든다.
- **감수하는 것:** 자유 질의를 만들 때 라우팅 계층을 새로 설계해야 한다(Notion 설계·계약의 `make_plan` 시그니처는 남아 있음).
- **다시 볼 조건:** 자유 질의(`/orchestrate/chat`)를 MVP에 넣거나 구현을 시작할 때.
- **바꿔야 하는 것:**
  - 삭제: `backend/orchestrator/graph.py`, `router.py`, `service.py`의 그래프 실행, `OrchestratorRequest.request_type` 기반 분기
  - `langgraph` 의존성: `requirements.txt`에서 제거. LangGraph를 쓰는 곳은 `orchestrator/graph.py`뿐이고, 토론(`debate_renewal`·레거시 `agents/debate`)은 쓰지 않으며 쓸 계획도 없다(유민 확인, #94)
  - 구현 계획 PR-4(토론 경로)·PR-8·PR-10(엔드포인트)에서 직접 호출 구조로, PR-12에서 잔여 정리

## 참고

- 오케스트레이터 기획서 1·2·3·11장
- 0012 (테이블 큐·워커), 0013 (시뮬레이션 별도 job)
- 의견을 준 사람: 유민 (토론 패키지 LangGraph 미사용 확인, #94)
