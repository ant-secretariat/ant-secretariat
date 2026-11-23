# Implementation Plan: 오케스트레이터·트렌드 리포트·인사이트보드 MVP 리빌드

**Branch**: `docs/001-orchestrator-trend-insight` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: [spec.md](spec.md), 기획서 v2.0 3종([오케스트레이터](../../docs/orchestrator/orchestrator-spec.md) · [트렌드 리포트](../../docs/trend-report/trend-report-spec.md) · [인사이트보드](../../docs/insight-board/insight-board-spec.md))

## Summary

세 에이전트를 기획서 v2.0과 계약 draft.5에 맞춰 다시 구현한다. 핵심은 세 가지다.

1. **오케스트레이터를 모든 진입점의 관문으로:** 관문1(종목 확정) → (토론만) precheck → 공통 봉투. 토론은 Supabase `agent_jobs`·`job_events`에 job을 만들고 SSE로 진행을 보낸다.
2. **숫자는 코드, 문장은 LLM + 검증:** 트렌드 리포트의 목표주가·인사이트보드의 배지는 코드가 계산하고, LLM 문장은 L1 검증을 통과해야만 노출한다.
3. **레거시 경로 정리:** Pinecone·SQLite 직접 접근을 없애고 데이터 함수(Supabase)만 쓴다.

자유 질의·플래너·도구 레지스트리·Langfuse는 Post-MVP다(계약 11/5 결정).

## Technical Context

**Language/Version**: Python 3.12 (backend), TypeScript (frontend, 타입 갱신만)

**Primary Dependencies**: FastAPI, Pydantic v2, LangGraph(기존 라우팅 유지), openai SDK(Upstage 호환), psycopg(데이터 함수 경유). 테스트 전용: `pyyaml`, `jsonschema` (research R9)

**Storage**: Supabase Postgres — 신규 `agent_jobs`·`job_events`·`uncovered_query_log` (R2). `users`는 SQLite 유지(범위 밖)

**Testing**: pytest + FastAPI TestClient. 데이터 함수·LLM은 monkeypatch로 대체. 계약 테스트는 `openapi.yaml` 스키마 검증(R9)

**Target Platform**: 단일 인스턴스 FastAPI 서버 (uvicorn)

**Project Type**: web-service (backend) + 기존 SPA(frontend)

**Performance Goals**: 토론 시작 p95 ≤ 1초, 트렌드 리포트 p95 ≤ 10초, 인사이트보드 p95 ≤ 3초(목표)

**Constraints**: PR 400줄 이하(팀 합의), 노출 주장 근거 연결 100%, 투자 권유 표현 0건, 모든 조회에 `as_of` 명시

**Scale/Scope**: 데모 규모(동시 사용자 수십 명), 커버 종목 T1 약 100개

미정 항목은 모두 [research.md](research.md)에서 결정했다. 담당자 확인이 남은 것은 R3(커버 판정, 수경)·R5(목표주가 임계값, 운영 DB)·R6(인증, 팀)이며, 결정대로 진행하다 바뀌면 문서를 함께 고친다.

## Constitution Check

*GATE: Phase 0 전 확인, Phase 1 후 재확인.*

| 원칙 | 확인 | 결과 |
| --- | --- | --- |
| I. 명세가 기준 | 기획서 v2.0 3종과 이 spec이 기준. 구현이 다르면 같은 PR에서 기획서 버전을 올린다 | ✅ |
| II. 계약 우선 | 계약에 없는 것(`BrokerView`, `VerificationSummary`, `REASON_POLICY` 표, `EntityResolution.companies` maxItems 3, 매크로 항목 ticker)은 **PR-0 계약 PR**에서 먼저 바꾸고 유민·수경 리뷰를 받는다. 공용 값은 `processing.enums`·`backend/contracts`에서 import | ✅ (PR-0 선행 조건) |
| III. 데이터 정직성 | 조회 실패 ≠ 데이터 없음(관문1 503, 인사이트보드 `error`, `mentioned_in_query` None), `as_of` 명시(look-ahead 금지), KST 날짜, 일부 실패 격리 | ✅ |
| IV. 근거와 고지 | 숫자는 코드, 주장마다 `evidence_ids`, L1 실패 시 철회, 금지 표현 공용 검사, 미커버 로그는 가린 문장·사용자 해시만 | ✅ |
| V. 수치로 채택 | 프롬프트·근거 선택 규칙은 품질에 영향 → PR-9·10에 고정 종목셋 기준선 수치(근거 연결률·철회율·지연) 첨부. 목표주가 임계값은 운영 DB 분포 첨부 | ✅ (PR 조건) |

위반 없음. Complexity Tracking 비움.

## Project Structure

### Documentation (this feature)

```text
docs/orchestrator/orchestrator-spec.md     # 에이전트 기획서 (버전 관리 대상)
docs/trend-report/trend-report-spec.md
docs/insight-board/insight-board-spec.md
specs/001-orchestrator-trend-insight/
├── spec.md          # 기능 명세 요약 (기획서 링크)
├── plan.md          # 이 문서
├── research.md      # Phase 0 결정
├── data-model.md    # Phase 1 엔티티·테이블·상태 전이
├── quickstart.md    # Phase 1 검증 시나리오
├── contracts/       # 계약 변경 목록 (원본은 docs/api/openapi.yaml)
└── tasks.md         # 다음 단계 (/speckit-tasks)
```

### Source Code (repository root)

```text
backend/
├── contracts/                 # 신규: 공용 계약 타입 (태은 소유)
│   ├── envelope.py            #   Envelope 5종, Reason, ResponseMeta, REASON_POLICY, make_reason
│   ├── entities.py            #   CompanyContext, Candidate, EntityResolution
│   └── jobs.py                #   JobStatus, JobEvent 타입
├── core/                      # #60: errors(→ REASON_POLICY 사용), config, logging_setup
├── verification/              # 신규: text_rules.py (금지 표현·자리표시, 토론과 공용)
├── orchestrator/
│   ├── companies.py           # resolve_companies (관문1) — resolve_company_context 대체
│   ├── uncovered.py           # log_uncovered_query
│   ├── jobs.py                # 토론 job 생성·재사용·한도, append_event, 시작 시 정리
│   ├── graph.py · router.py   # trend_report 경로 추가, 노드가 Envelope 반환
│   ├── schemas.py · service.py
├── functions/agent_jobs.py    # Supabase 저장소로 교체 (SQL은 여기에만)
├── api/
│   ├── orchestrator.py        # insight-board · debate · trend-report (봉투)
│   ├── jobs.py                # GET /jobs/{job_id}/events (SSE)
│   ├── session.py             # current_user_id(), 쿠키 발급
│   └── trend_report.py        # /agents/trend-report (deprecated, FE 전환 후 삭제)
├── agents/insight_board/      # data_client · badges · summary(신규) · comment_generator · service
├── agents/trend_report/       # context(신규) · evidence(신규) · target_price(신규) · generator · verify(신규) · gaps(신규) · service
│                              # 삭제: pinecone_retriever.py · run.py · data_agent_client.py
└── tests/
    ├── contract/              # openapi.yaml 스키마 검증
    └── test_*.py
supabase/migrations/            # agent_jobs · job_events · uncovered_query_log
frontend/src/                   # types.ts · api/client.ts (봉투·Badge·Claim, trend-report 경로 전환)
```

**Structure Decision**: 기존 폴더 역할(#59: `api`=라우터, `orchestrator`=흐름, `functions`=저장소, `agents`=도메인)을 유지하고 공용 타입만 `backend/contracts/`로 모은다. 새 패키지·워크스페이스는 만들지 않는다.

## PR 순서

팀원 연동을 빨리 풀어 주는 순서다. 각 PR은 400줄 이하, 테스트 포함. ★은 다른 담당이 기다리는 PR.

| # | PR | 내용 | 선행 | 기다리는 사람 |
| --- | --- | --- | --- | --- |
| PR-0 | 계약 draft.6 | `REASON_POLICY` 표(OQ-1), `EntityResolution.companies` maxItems 3, `BrokerView`·`VerificationSummary`, 매크로 항목 `ticker="macro"`, 계약 테스트(R9) | — | 유민·수경 리뷰 |
| PR-1 ★ | 공통 봉투 | `backend/contracts/envelope.py`·`entities.py`, `core/errors`가 `REASON_POLICY` 사용 | PR-0 | 전원 (응답 형식) |
| PR-2 ★ | job 저장소 | 마이그레이션 `agent_jobs`·`job_events`, `functions/agent_jobs.py` Supabase 교체, `JobStatus`, `append_event`(seq 단일 지점), 시작 시 정리 | PR-1 | 유민 (`run_debate`가 이벤트 기록) |
| PR-3 ★ | 관문1 | `resolve_companies`, `mentioned_in_query`, 커버 판정, `uncovered_query_log` 마이그레이션·`log_uncovered_query` | PR-1 | 유민 (precheck 입력) |
| PR-4 ★ | 토론 경로 | precheck 호출, 재사용·동시 한도, `job_started`/`rejected` 봉투, `run_debate` 어댑터(레거시 → renewal 교체 지점 하나) | PR-2, PR-3 | 유민·수경 (시뮬레이션 상태) |
| PR-5 ★ | SSE | `GET /jobs/{job_id}/events`, `Last-Event-ID`, ping, 종료 후 닫기 | PR-2 | FE |
| PR-6 | 세션 | HMAC 쿠키 발급·검증, `user_id` 바디 병행 | PR-1 | FE (R6 팀 결정 후) |
| PR-7 | 공용 텍스트 검사 | `backend/verification/text_rules.py`, 토론 L1 import 교체 | — | 유민 리뷰 |
| PR-8 | 인사이트보드 | 종목별 실패 판정, `Badge`, `summarize_for_comment`, `verify_comment`, `InsightBoardResult`, 봉투 라우트 | PR-1, PR-7 | FE |
| PR-9 | 트렌드 리포트 ① 데이터 | `get_agent_context` 경로, `select_evidence`, `compute_target_price_trend`, 레거시 삭제 (+운영 DB 임계값 분포) | PR-1, #53 | — |
| PR-10 | 트렌드 리포트 ② 생성·검증 | `generate_cards`(구조화 출력), `verify_cards`, `fill_card_gaps` S1~S3, `data_tier` 정책, status, `/orchestrate/trend-report` (+기준선 수치) | PR-9, PR-7 | FE |
| PR-11 | FE 전환 | 봉투 처리, `Badge`·`Claim` 렌더링, trend-report 경로 전환, SSE 구독 | PR-4·5·8·10 | — |
| PR-12 | 정리 | `/agents/trend-report` 삭제, `resolve_company_context`·SQLite `agent_jobs` 잔여 제거 | PR-11 | — |

### 에이전트별 귀속

| 귀속 | PR | 기획서 |
| --- | --- | --- |
| **공통 인프라** (세 에이전트와 토론이 같이 씀, 태은 소유) | PR-0 계약, PR-1 공통 봉투, PR-6 세션, PR-7 공용 텍스트 검사, PR-11 FE 전환 | 오케스트레이터 기획서 4·8장, 트렌드 리포트 기획서 6장 |
| **오케스트레이터 (C)** | PR-2 job 저장소, PR-3 관문1, PR-4 토론 경로, PR-5 SSE, PR-12 정리(오케스트레이터 쪽) | [orchestrator-spec.md](../../docs/orchestrator/orchestrator-spec.md) |
| **트렌드 리포트 (D)** | PR-9 데이터·근거·목표주가, PR-10 생성·검증·보완, PR-12 정리(`/agents/trend-report` 삭제) | [trend-report-spec.md](../../docs/trend-report/trend-report-spec.md) |
| **인사이트보드 (E)** | PR-8 | [insight-board-spec.md](../../docs/insight-board/insight-board-spec.md) |

**일정 (12/6 범위·일정 점검 기준):** PR-0~5를 11/30까지(토론 연동 시작), PR-6~8을 12/4까지, PR-9~10을 12/6 점검일에 리뷰 중, PR-11~12를 12월 둘째 주. 12/6에 PR-9·10이 리뷰에 못 들어가면 트렌드 리포트는 PR-9(코드 계산 목표주가 + 기존 생성) 상태로 MVP를 내고 PR-10을 뒤로 미루는 안을 점검일에 결정한다.

## 위험과 대응

| 위험 | 영향 | 대응 |
| --- | --- | --- |
| #53 머지 지연 (`data_tier`·`intent`) | PR-9 막힘 | `data_tier_for()`로 직접 계산하는 대체 경로를 PR-9에 둔다 |
| `debate_renewal`의 `run_debate` 미완성 | PR-4 검증 불가 | 어댑터 한 곳에서 레거시 `agents/debate`를 부르고, renewal 준비되면 그 줄만 바꾼다 |
| Upstage 구조화 출력 미지원 | PR-10 파싱 실패율 | JSON 모드 + Pydantic 검증 + 1회 재요청 (R8) |
| 인증 결정 지연 (OQ-8) | FE가 `user_id`를 계속 보냄 | 바디 병행 허용으로 다른 PR을 막지 않음 |
| 트렌드 리포트 10초 초과 | FN-TR-01 미달 | 데이터 병렬 조회(R12), 보완 예산 +3초 상한, 측정 후 근거 상한 축소 |

## Complexity Tracking

해당 없음.
