*ant-secretariat · Agent F · rebuild spec · v3.0*

# 토론 에이전트 (Agent F) 리빌드 기획서

> 2026-11-22 HTML 원본(`debate-agent-rebuild-spec-v3.0.html`)을 Markdown으로 옮겼고, 이후에는 이 파일이 기준이다. 내용은 HTML 마지막 판(ADR 0009·비교 모드 종목별 판정 반영)과 같다.

Bull/Bear/Judge 토론 파이프라인 리빌드 설계. 멀티에이전트 설계 최종본(10/14)의 팀 간 계약을 반영해 단일·비교 모드, 작업 큐 실행, 공용 계약 정렬까지 확정한 버전.

> **✅ 확정 기준** — 멀티에이전트 설계 최종본(태은, 10/14)의 5.1 확정 계약 · 5.2 논의 이슈 Q1~Q14 결론 · 8장 수정안 대조 결과를 반영. 온톨로지 상세는 「온톨로지 프로덕트 기획서 v1.2」를 따름.

| 항목 | 값 |
| --- | --- |
| 에이전트 ID | Agent F |
| 담당자 | 이유민 |
| 버전 | v3.0 |
| 작성일 | 2026-10-21 |
| 상태 | 설계 확정 · 구현 착수 대기 |
| 일정 | 팀 협의 후 재확정 |

> **v2.3 → v3.0 주요 변경**
> ① D3 비교 모드를 이번 범위에 포함 (보류 1 해소) · ② Judge 적합도 label 미노출, 성향은 `points_to_check`·`caution`에만 반영 (보류 2 해소) · ③ 실행은 fire-and-forget 대신 Postgres 작업 큐 + 체크포인트 · ④ 데이터는 도구 레지스트리 경유 · ⑤ 사유 코드·다음 행동을 `envelope.py` 이름으로 정렬, `AgendaId`·`ReasonCode` 공용 열거형 import · ⑥ `simulation_handoff` 필드 삭제 · ⑦ 벡터 저장소 pgvector, 목표주가 KIS 컨센서스 · ⑧ 검증 레이어(L1 → 근거 부족 루프 → 1회 수정) 추가 · ⑨ 온톨로지 절은 온톨로지 기획서 참조로 교체

### ⚠️ 최종본 중 수정을 요청하는 항목

**요청 1 — SSE 이벤트 단위: 토큰 대신 노드·주장 단위로**

> 최종본은 LangGraph `stream_mode="messages"`를 중계하되 워커 간 전달은 `job_events` 테이블 + `pg_notify`로 한다고 되어 있음. 이 구조에서 토큰 하나하나를 테이블에 쓰면 토론 1건에 수천 행이 생기고 DB 쓰기가 병목이 됨. 게다가 Bull·Bear·Judge 출력은 `json_schema` strict JSON이라 토큰 조각을 FE가 그대로 렌더링할 수도 없음. → 이벤트를 단계·주장 단위로 적재하고 FE는 주장 단위로 화면을 채우는 방식을 제안함 (D8). **결론(ADR 0009, 계약 draft.5):** 단계 이벤트 `job_started` · `data_collected` · `bull_completed` · `round2_started` · `bear_completed` · `verifying` · `judge_completed`, 주장 이벤트 `claim_completed`, 종료 이벤트 `completed` / `failed`. 서버 안 전달은 `pg_notify` 없이 `job_events`를 1초마다 조회해 SSE로 보냄.

**요청 2 — 연동 계약 표(6장)의 `get_ontology_context` 반환값 정정**

> 표에는 `get_ontology_context`가 "관계 경로·`evidence_coverage`"를 반환한다고 되어 있으나, `evidence_coverage`는 Phase B `get_reasoning_path`의 `ReasoningPath` 필드임. Phase A 반환은 `OntologyContext`(관계·매크로 노출·이슈·경쟁사·요약)이므로 표 수정 필요.

## 01 · 역할 및 인터페이스

*에이전트 책임 범위, 실행 위치, 입출력 계약.*

### 1.1 에이전트 역할

선택된 종목에 대해 Bull·Bear·Judge가 아젠다별 순차 토론을 수행하고 최종 브리핑을 생성. 종목이 1개면 **단일 모드**, 2개면 **비교 모드**(D3). 근거와 판정(`verdict`·`stance`)은 사용자 성향과 무관하게 동일하고(사실 층), 성향은 Judge의 `points_to_check`·`caution` 강조에만 반영함(판단 층). 적합/부적합 label은 노출하지 않음.

> **job 상태:** `queued` → `running` → `debate_completed` → (단일 모드) `simulation_pending` → `simulation_running` → `completed` / `failed`. 토론은 검증 레이어 통과 후 `simulation_pending`으로 바꾸고 끝남. 시뮬레이션은 사용자가 버튼을 누르면 오케스트레이터가 `run_simulation(ticker, user_id, job_id)`를 큐에 등록하고, 시뮬레이션이 `job_id`로 토론 결과를 조회해 `macro`·`risk` 아젠다를 ID로 꺼냄. 비교 모드는 `debate_completed`에서 종료(시뮬레이션 없음).

### 1.2 실행 위치와 호출 방식

| 구분 | 방식 | 비고 |
| --- | --- | --- |
| precheck | 오케스트레이터가 job 생성 전 동기 호출 | 룰 기반 순수 함수, 수 ms. LLM 없음 |
| run_debate | Postgres 작업 큐 워커가 실행 | PgQueuer 1순위·Procrastinate 대안(스파이크 후 결정). LangGraph `PostgresSaver` 체크포인트로 재시작 시 이어서 실행 |
| 데이터 접근 | 도구 레지스트리 `invoke()` | 직접 import 금지. 인자 검증·권한·Langfuse span이 레지스트리에서 처리됨 |
| 진행 상황 | `job_events` 1초 조회 → SSE (ADR 0009) | 보조 경로 `GET /debate/jobs/{id}` 폴링 |
| LLM | Upstage Solar, OpenAI 호환 API | `json_schema` strict 출력 |

### 1.3 시그니처

```
# 공용 열거형 — data-pipeline 제공, 문자열 하드코딩 금지
from data_pipeline.contracts import AgendaId, DataTier
# backend 내부 계약 — backend/contracts/
from backend.contracts import ReasonCode, NextAction, EntityResolution, PrecheckResult, Evidence, Claim, ResponseMeta

# 관문2·3 — 토론 에이전트 소유. 오케스트레이터가 job 생성 전 동기 호출
def precheck(query: str, companies: list[CompanyContext]) -> PrecheckResult:
    # 관문2: 아젠다 풀 키워드 사전 매핑 (룰). 매핑 실패 → reject(out_of_scope_topic)
    # 관문3: intent_data_sources.json(시작 시 1회 로드) 기준 아젠다별 데이터 확인
    #        tier·data_tier 확인 → T2는 reject(data_collecting), T0은 reduced
    # 비교 모드: 두 종목 모두 데이터가 있는 아젠다만 축으로 허용
    ...

class PrecheckResult(BaseModel):
    verdict: Literal["full", "reduced", "reject"]
    reject_reason: ReasonCode | None        # envelope.py 이름 그대로
    mode: Literal["single", "compare"]   # EntityResolution.mode 승계
    allowed_agendas: list[AgendaId]          # 목표 3개 (비교 모드에서는 축)
    excluded: list[ExcludedAgenda]           # 범위 축소 고지용 (agenda_id, reason)
    selection_reason: str                    # FE 상단 한 줄
    matched_intents: list[AgendaId]          # 아젠다 선택셋 평가용
    flags: list[Literal["investment_advice_request", "stale_data"]]
    dictionary_version: str                  # 키워드 사전 + intent_data_sources 버전

# 토론 진입점 — 작업 큐 워커가 호출. 모드는 precheck.mode로 결정, 내부 재판정 없음
async def run_debate(
    companies: list[CompanyContext],   # 1개(single) 또는 2개(compare)
    user_id: str,                      # 세션에서 주입, 클라이언트 값 신뢰 안 함
    query: str,
    precheck: PrecheckResult,
    job_id: str,
) -> DebateResult
```

관문1 `EntityResolution`은 오케스트레이터(태은) 소유이며 공용 계약 정의를 그대로 사용함: `status`(ok·ambiguous·not_found·uncovered·too_many·partial_covered), `companies`(최대 2), `ambiguous`(후보: 섹터·시총), `uncovered`, `mode`.

### 1.4 공용 계약 위치 (최종본 8장 제안안)

| 위치 | 타입 |
| --- | --- |
| `backend/contracts/` | `ReasonCode` · `NextAction` · `EntityResolution` · `PrecheckResult` · `Evidence` · `Claim` · `ResponseMeta` |
| data-pipeline | `AgendaId` · `resolve_company` 반환 모델 · `data_tier` (backend가 import, 기존 의존 방향 유지) |
| FE ↔ API | FastAPI OpenAPI 스키마에서 TS 타입 생성 |

### 1.5 거절 응답 봉투

```
# precheck verdict=reject 시 오케스트레이터가 반환 (job 생성 없음)
{
  "status": "rejected",
  "reason": { "code": ReasonCode, "message": str },
  "next_action": { "type": NextAction, "payload": any },
  "meta": ResponseMeta
}
```

> **이름 정렬:** v2.3의 `out_of_scope`·`not_found`·`suggest_alternatives`·`narrow_scope` 등 자체 이름은 폐기하고 `envelope.py`의 이름(`out_of_scope_topic`, `company_not_found`, `choose_supported_topic`, `check_back_later` 등)을 그대로 씀. 전체 대응표는 D4.

### 1.6 공통 타입 (변경 없음)

```
class Evidence(BaseModel):
    evidence_id: str                 # "S1" — 본문 [S숫자]와 대응
    chunk_id: str
    document_type: Literal["report","news","disclosure","macro","structured"]
    title: str; source: str; author_org: str | None
    date: str; url: str | None
    content_preview: str
    evidence_source: Literal["original", "gap_fill"] = "original"

class Claim(BaseModel):
    claim_id: str
    text: str                        # 숫자는 {{placeholder}}, 코드가 get_metric 값으로 치환
    claim_type: Literal["numeric", "event", "opinion", "table"]
    evidence_ids: list[str]

class ResponseMeta(BaseModel):
    trace_id: str; data_as_of: str; generated_at: str
    prompt_version: str | None = None; model: str | None = None
```

### 1.7 출력 스키마 (DebateResult)

```
{
  "meta": ResponseMeta + { "mode": "single"|"compare", "companies": [{ticker, company, sector, data_tier}] },
  "scope": { "verdict": "full"|"reduced", "excluded": [{agenda_id, reason}], "selection_reason": str },
  "flags": ["investment_advice_request"|"stale_data"],
  "selected_agendas": list[AgendaId],

  # 단일 모드
  "agendas": [{
    "id": AgendaId, "title": str,
    "bull": { "claims": list[Claim], "confidence": str },
    "bear": { "bull_claim_ref": str, "agreed_points": list[str], "claims": list[Claim], "confidence": str },
    "verdict": { "winner": "bull"|"bear"|"neutral", "reason": str, "score": {bull, bear} },
    "rebuttal_round": bool
  }],

  # 비교 모드 (D3) — mode="compare"일 때만
  "comparison": { "axes": [{
    "agenda_id": AgendaId, "comparable": bool, "not_comparable_reason": str | null,
    "as_of_dates": {ticker_a, ticker_b}, "as_of_gap_warning": bool,
    "per_company": { ticker: { "bull": {...}, "bear": {...} } },
    "axis_verdict": { "stronger": ticker|"tie", "reason": str }
  }] },

  "evidence": list[Evidence],
  "judge": {
    "user_profile": { "risk_profile", "investment_goal" },
    "overall_verdict": {          # 단일 모드만. 비교 모드는 per_company_verdict
      "stance": "bullish"|"neutral"|"bearish",   # 성향 불변 (사실 층)
      "confidence", "bull_score", "bear_score",
      "final_brief": str,
      "caution": str,                 # 성향 반영 강조 (판단 층)
      "points_to_check": list[str]      # 성향 반영 강조, 매매 판단 없음
    },
    "per_company_verdict": { ticker: overall_verdict와 같은 모양 }   # 비교 모드만. 두 종목 모두 하나씩
  }
}
# 삭제: simulation_handoff — 시뮬레이션이 job_id로 직접 조회하므로 중복 관리하지 않음
```

## 02 · AS-IS vs TO-BE

*1차 구현(7월) 대비 무엇이 바뀌는가.*

| 항목 | AS-IS | TO-BE | 상태 |
| --- | --- | --- | --- |
| 사전 판정 | 없음, 항상 실행 | job 생성 전 관문1(오케스트레이터) + precheck(토론) (D1) | `신규` |
| 아젠다 구성 | 고정 3개 | 아젠다 풀 6개(`AgendaId`) 중 질의 기반 3개 (D2) | `신규` |
| 다종목 비교 | 없음 (1종목만) | 최대 2종목, 축 단위 대칭 검색 + 종목별 Bull·Bear + Judge 축별 비교 (D3) | `신규` |
| Bear 반박 | Bull 출력 주입만 | Bull Claim 인용 반박 + 인정 여지 `agreed_points` (D6) | `개선` |
| 라운드 수 | 1회 고정 | 기본 1회 + 점수차 작은 아젠다만 2라운드 (D5, 단일 모드) | `신규` |
| 실행 인프라 | asyncio fire-and-forget (재시작 시 유실) | Postgres 작업 큐 + `PostgresSaver` 체크포인트 | `개선` |
| 데이터 접근 | 함수 직접 import, Pinecone | 도구 레지스트리 경유, pgvector, 지표는 `get_metric(as_of)` | `개선` |
| 출력·검증 | json.loads, 검증 없음 | Pydantic + strict 출력 (D7), 검증 레이어 L1 → 근거 부족 루프 → 1회 수정 | `신규` |
| 진행 표시 | 2.5초 폴링 | SSE (`job_events` 경유, 노드·주장 단위) (D8) | `개선` |
| 개인화 | 성향별로 결론 톤 변경 | 사실 층 불변, 성향은 `points_to_check`·`caution`에만 | `개선` |
| 온톨로지 | 없음 | 기능 플래그 뒤에서 아젠다별 1회 조회·공유 (기본 꺼짐) | `신규` |
| 평가 체계 | 없음 | 기준선 비교 실험 · 거절셋 · 골든셋 등 7종 (D10) | `신규` |
| 시뮬레이션 연동 | `agendas[1]` 인덱스 자동 전달 | `simulation_pending` + 버튼 → `run_simulation(ticker, user_id, job_id)` | `개선` |
| 지원 종목 | 7개 하드코딩 | T1 전체 실행 / T0 범위 축소 / T2 수집 중 거절 | `개선` |

## D1 · 사전 판정 흐름

*job을 만들기 전에 답할 수 있는 질의인지 결정적으로 판정.*

> **확정:** 판정 로직 소유(토론 에이전트)와 실행 시점(job 생성 전)을 분리. 오케스트레이터는 라우팅만 하고 토론 도메인 지식은 갖지 않음. 관문2는 LLM 없이 룰 + 키워드 사전으로 판정하며, 경량 모델은 거절셋 측정 결과 룰이 놓치는 비율이 높을 때만 승격.

- `INPUT` **사용자 질의 수신 (오케스트레이터, job 생성 전)** — 버튼 경로 `POST /orchestrate/debate` 또는 채팅 경로 `POST /orchestrate/chat`
- `관문1` **종목 확정 — 오케스트레이터 (태은)** — `extract_company_mentions`로 종목 식별, 커버 여부·비교 개수 판별. 애매하면 `clarification_needed`로 후보(채팅 5개, 섹터·시총 포함)를 되묻고 자동 추측하지 않음. → `EntityResolution`
- `precheck` **관문2 + 관문3 — 토론 에이전트 (유민)** — 관문2: 아젠다 풀 키워드 사전 매핑 → 실패 시 `out_of_scope_topic` 관문3: `intent_data_sources.json` 기준 아젠다별 데이터·신선도·`data_tier` 확인 → T1 full / T0 reduced / T2 `data_collecting` 거절 / 노후 데이터는 `stale_data` flag → `PrecheckResult`
- `분기` **세 가지 결과 — 모두 job 생성 전** — 🟢 full — job 생성 → 큐 등록 → `job_started` · 🟡 reduced — 같은 흐름 + `scope` 고지 · 🔴 reject — job 없이 `rejected` + `next_action` 즉시 반환, 미커버 로그 적재. T2는 거절과 동시에 오케스트레이터가 `ensure_company_data`로 수집 예약(중복 예약 방지)

| 컴포넌트 | 소유 | 담당 |
| --- | --- | --- |
| 관문1 · `EntityResolution` · 되묻기 상태 `pending_clarification` | 오케스트레이터 | 태은 |
| `precheck()` · 키워드 사전 · `PrecheckResult` | 토론 에이전트 | 유민 |
| `intent_data_sources.json` · `ensure_company_data` | 데이터 에이전트 | 수경 |

## D2 · 아젠다 풀 + 질의 기반 선택

*고정 3개는 질문을 반영하지 못하고, 완전 가변은 버전 간 비교가 불가능함. 유한한 풀에서 고르는 방식으로 평가셋 구축이 가능해짐.*

> **확정 (최종본 5.2 Q12):** 아젠다 ID = `intent` 값. `AgendaId` 열거형 하나를 precheck 키워드 사전·`intent` 매핑·온톨로지 경로·시뮬레이션 상수·플래너가 모두 import함.

- **valuation · 실적 및 밸류에이션** — 비싼가·싼가, 실적, 목표주가(KIS 컨센서스) (기본 포함)
- **macro · 산업 및 매크로 환경** — 업황, 금리·환율, 경쟁 구도 (기본 포함)
- **risk · 리스크 요인** — 위험, 하락 가능성, 우려 (기본 포함)
- **growth · 성장 동력** — 신사업, 수주, 증설, 신제품 (선택 포함)
- **shareholder_return · 주주환원** — 배당, 자사주 (선택 포함)
- **flow · 수급·투자자 동향** — 외국인·기관 매매 (재확인 중)

선택 규칙: 기본 3개가 기본값. "배당·자사주" 언급 시 `shareholder_return`이 `valuation`을 대체, "신사업·증설" 언급 시 `growth` 추가, 최대 3개 유지. `flow`는 `investor_flow_daily` 확보로 활성화 여부를 수경과 재확인함.

## D3 · 비교 모드 (2종목)

*최종본 5.1에서 이번 범위로 재확정(10/14). 비교 모드 상세 설계는 이 기획서가 소유함.*

#### P-D3 · 두 종목을 비교하면 Bull/Bear 역할이 깨진다

**문제 정의**

단일 종목 토론은 Bull=강세론자, Bear=약세론자로 역할이 명확함. A vs B를 한 토론으로 돌리면 "A의 강세 = B의 약세"가 되어 무엇에 대한 강세인지 모호해지고, 순서·서술량에 따라 한쪽이 유리해지는 편향도 생김.

**OPTIONS**

- **A** 한 토론 안에서 Bull=A 옹호, Bear=B 옹호
- **B ✓** 종목마다 같은 축의 Bull·Bear를 따로 실행하고, Judge가 축 단위로 두 종목을 비교
- **C** 토론 없이 축별 비교 리포트만 생성

> **B 선택:** A는 역할 붕괴 문제를 그대로 안고 감. C는 서비스의 핵심인 교차 검증이 사라짐. B는 단일 모드의 Bull→Bear 구조를 종목별로 재사용하므로 프롬프트·스키마·평가셋을 그대로 쓸 수 있고, 비교 판단은 Judge 한 곳에만 둠. C는 B의 한쪽 실행이 실패했을 때 쓰는 대체 경로가 아니라 단일 분석 전환으로 처리함(아래 부분 실패).

### 실행 구조 — 축 단위 병렬 팬아웃

- `축 선택` **precheck가 비교 축 3개 결정** — 같은 아젠다 풀·키워드 사전 사용. 두 종목 모두 데이터가 있는 아젠다만 축으로 허용(티어가 다르면 교집합)
- `대칭 검색` **축마다 같은 질의 템플릿으로 A·B를 함께 검색** — 기업당 청크 예산 고정. 한쪽 근거가 없으면 해당 축은 `comparable=false`로 표기하고 비교하지 않음
- `병렬` **종목별 Bull → Bear (종목 간 동시 실행)** — 종목 안에서는 Bear가 Bull을 인용하므로 순차, 종목끼리는 병렬로 지연 단축
- `JUDGE` **축별 비교 판정 + 종합** — 축마다 `axis_verdict.stronger`(A·B·tie)와 근거. A·B 제시 순서는 무작위화. "어느 쪽을 사라"가 아니라 "이 축에서 근거가 더 강한 쪽"만 판정. 종합 판정(stance·점수·브리핑)은 종목마다 하나씩 `judge.per_company_verdict`에 담고, 두 종목을 묶은 단일 stance는 두지 않음(유민 결정 2026-11-22, 태은 #23 리뷰)

| 규칙 | 내용 |
| --- | --- |
| 기준일 격차 | 축마다 두 종목의 `as_of`를 나란히 표기, 격차가 임계값을 넘으면 `as_of_gap_warning` |
| 지표 기준 불일치 | 연결/별도, 추정/확정이 다르면 수치 비교 대신 서술로 처리 |
| 부분 실패 | 한쪽 검색·생성이 실패하면 비교를 만들지 않고 성공한 종목의 단일 분석으로 전환 + 사유 고지 |
| 범위 제한 | 조건부 2라운드(D5) 끔, 시뮬레이션 버튼 없음(`debate_completed`에서 종료), 온톨로지 플래그는 단일 모드에서 효과 확인 후 별도로 켬 |
| 거절 | 3종목 이상·한쪽 미커버는 관문1에서 거절 (D4) |

## D4 · 거절·축소 유형과 응답 코드

*거절도 품질 지표 — 오답변율 ≤5%, 과잉거절률 모니터링. 코드 이름은 `envelope.py`를 기준으로 함.*

| 상황 | 판정 지점 | 동작 | `reason.code` / `next_action` |
| --- | --- | --- | --- |
| 종목 식별 실패 | 관문1 | job 생성 안 함 | `company_not_found` / 후보 선택 |
| 종목 애매 | 관문1 | 거절이 아니라 되묻기 | `clarification_needed` 봉투 |
| 미커버 종목 | 관문1 | job 생성 안 함 · 미커버 로그 | envelope.py 이름 확인 필요 / 대안 종목 제시 |
| 비교 3종목 이상 | 관문1 | job 생성 안 함 | envelope.py 이름 확인 필요 / 두 개 선택 |
| 비교 한쪽만 커버 | 관문1 | job 생성 안 함 | envelope.py 이름 확인 필요 / 커버된 쪽 단일 분석 제안 |
| 주제 범위 밖 | precheck 관문2 | job 생성 안 함 · 로그 | `out_of_scope_topic` / `choose_supported_topic` |
| T2 수집 중 | precheck 관문3 | job 생성 안 함 · 오케스트레이터가 `ensure_company_data` 예약 | `data_collecting` / `check_back_later` (알림·ETA 없음) |
| 데이터 부족 | precheck 관문3 | reduced, 남는 아젠다가 없으면 reject | reject 시 envelope.py 이름 확인 필요 |
| T0 종목 | precheck 관문3 | derived 기반 reduced 실행 | — (`scope.excluded`로 고지) |
| 데이터 노후 | precheck 관문3 | 실행 + `stale_data` flag | — ("N일 전 자료 기준" 배지) |
| 투자 권유 요청 | precheck 관문2 | 실행 + `investment_advice_request` flag → Judge 답변 범위 제한 | — (매매 판단 안 함 고지) |

> **새 거절 상황**이 생기면 유민이 제안하고 응답 계약(`ReasonCode`)에 추가한 뒤 사용함 (최종본 5.2 Q3).

## D5·D6 · 라운드 수 & Bear 반박 강도

*순차 + 생성자–비평자 구조, 2라운드는 제한된 루프.*

- **D5 변경**: 기본 1라운드 + Judge의 `bull_score`/`bear_score` 차이가 임계값 이하인 아젠다만 재반박. 단일 모드에만 적용.
- **D5 근거**: 라운드를 늘린 이득은 3라운드 부근에서 포화. 필요한 아젠다에만 적용해 비용 통제. 라운드 수별 루브릭 점수·토큰·지연을 기록해 비용–품질 곡선으로 임계값 결정.
- **D6 결정**: "근거가 부족하면 Bull 주장을 일부 인정해도 된다"를 Bear 프롬프트에 명시, `agreed_points`로 기록. 억지 반박 강제는 정확도를 낮춤.
- **모니터링**: Judge의 `neutral` 판정이 한 번도 나오지 않으면 판정이 형식적이라는 신호 → 프롬프트 조정.

## D7·D8 · 구조화 출력 & 진행 스트리밍

*출력 형식 보장과 진행 상황 전달.*

#### P-D7 · json.loads 단일 재시도로는 부분 실패·Rate Limit을 처리하지 못함

- **A** 현행 유지
- **B ✓** Pydantic 스키마 + Solar `json_schema` strict + 에러 유형별 재시도
- **C** Pydantic AI 전면 도입

> **B 선택:** 429·5xx·타임아웃만 지수 백오프+지터, 4xx는 즉시 실패. 스키마 검증 실패 시 부분 결과를 보존. strict 출력도 필드 의미까지 보장하지 않으므로 Pydantic 검증은 별도로 유지. C는 의존성 대비 제어권이 줄어듦.

#### P-D8 · 수 분짜리 토론을 폴링으로 보여주면 대기 구간이 길다

- **A** 폴링 간격 단축
- **B** SSE로 토큰 단위 중계
- **C ✓** SSE로 단계·주장 단위 이벤트 중계 (`job_events` 1초 조회)

> **C 선택:** 워커와 API가 분리돼 이벤트가 `job_events` 테이블을 거치므로, 토큰 단위로 쓰면 토론 1건에 수천 행이 생김. 출력이 strict JSON이라 토큰 조각은 화면에 그대로 쓸 수도 없음. 이벤트는 단계 이벤트 `job_started` · `data_collected` · `bull_completed` · `round2_started` · `bear_completed` · `verifying` · `judge_completed`, 주장 이벤트 `claim_completed`, 종료 이벤트 `completed` / `failed`로 정의하고(계약 draft.5), FE는 주장 카드를 하나씩 채움. 2종목 비교에서는 종목별 이벤트 payload에 `ticker`를 넣고, 한 job의 `seq`는 그 job을 가진 워커 한 곳에서만 매김. 화면 순서는 Bull 완료 → Bear → Judge (Bear가 Bull을 입력으로 받는 구조적 순차). 최종본의 토큰 중계와 다른 점은 ADR 0009(PR #43)로 해소됨(미결 Q2 종결).

## D9 · 비용 상한

*측정 먼저, 상한은 그 다음.*

- **추적**: Langfuse Cloud Hobby (무료, 셀프호스팅 서버 불필요, 공통 인프라 담당 태은). 모든 LLM·도구 호출에 span, 응답 `meta.trace_id`로 연결.
- **실측 시점**: 토론이 처음부터 끝까지 동작하는 시점. 생략하지 않음 — 큐 동시 실행 수와 토론당 토큰 상한의 근거가 됨.
- **정할 값**: ① 토론 1건당 토큰 상한(단일·비교 따로) ② 사용자당 일일 실행 횟수 ③ 큐 동시 실행 수 ④ 초과 시 동작(대기 또는 거절)
- **모델 분리**: Judge → 상위 모델 / 요약·분류 → 경량 모델 / precheck → LLM 없음(룰).

## 검증 · 검증 레이어

*생성 결과를 사용자에게 내보내기 전에 결정적으로 거르는 게이트.*

- `L1` **결정적 검사** — 스키마 일치 · 모든 Claim의 `evidence_ids`가 실제 Evidence에 존재 · `{{placeholder}}` 숫자를 `get_metric` 값으로 치환했는지 · Bear의 `bull_claim_ref`가 실존 claim_id인지 · 매매 권유 표현 금지어
- `루프` **근거 부족 루프** — 근거 없는 Claim만 골라 추가 검색, 보완 근거는 `evidence_source="gap_fill"`로 표기
- `수정` **1회 수정** — 그래도 실패한 항목만 1회 재생성. 여전히 실패하면 해당 Claim을 제외하고 `partial`로 고지

## 온톨로지 · 온톨로지 연동 방식

*노드·엣지·평가 등 내부 설계는 「온톨로지 프로덕트 기획서 v1.2」가 원본. 여기에는 토론 에이전트가 지켜야 할 연동 규칙만 둠.*

- **호출**: 도구 레지스트리의 `get_ontology_context(ticker, agenda_id)`. 토론 job에서 아젠다별 1회 호출 후 그래프 상태에 캐시, Bull·Bear·Judge가 같은 결과 공유. 입장별 필터링 없음, 역할 차이는 프롬프트로 반영.
- **플래그**: 기본 꺼짐. 꺼져 있으면 호출하지 않음. 관계 종류 × 에이전트 단위로 꺼짐 → 그림자 모드 → 켜짐 순서.
- **weight**: 실제 회귀 계수가 들어오기 전까지 `source="placeholder"`이며 플래그를 켜지 않음. 프롬프트에는 "상관 기반 민감도"로만 표현하고 인과로 쓰지 않음.
- **지표**: PER·PBR·ROE·부채비율 등 매일 바뀌는 값은 그래프에서 읽지 않고 `get_metric(ticker, metric_id, as_of)`로 조회.
- **성향**: 탐색 결과는 성향과 무관. Judge가 성향으로 채점을 바꾸지 않음.

## D10 · 평가셋 & 측정 지표

*"왜 멀티에이전트 토론인가"에 데이터로 답할 수 있어야 함.*

| 평가셋 | 구성 | 지표 | 우선순위 |
| --- | --- | --- | --- |
| 기준선 비교 실험 ★ | 같은 질문·같은 근거·같은 모델(Solar)로 (a) 토론 (b) 단일 LLM 장단점 요약 생성. 공통 이진 루브릭 5~6항목, 아젠다별로 고르게 30~50문항, 순서 무작위 블라인드, 가능하면 채점자 2명 | 루브릭 점수 이득 ÷ 토큰·지연 배수, 채점자 일치율 | 1순위 |
| 거절셋 ★ | 라벨은 `ReasonCode`. 사유별 10~20건 + 과잉 거절 확인용 정상 경계 질의 | 오답변율 ≤5% · 과잉거절률 | 1순위 |
| 검색 골든셋 | 수경 마스터(`search_golden_set`), 스냅샷 태그로 고정해 결과와 함께 기록. `agenda_id`·`reviewed`·`is_active`, 미검토 행 제외 | Recall@5/20 · nDCG@10 | 2순위 |
| 토론 루브릭셋 | 완료 토론 50~100건 사람 채점. 관계 질문 하위셋은 온톨로지 켬/끔 비교에 사용 | 근거 인용·수치 정확성·반론 대응 | 2순위 |
| 비교셋 | 같은 섹터 종목 쌍 + 축별 기대 근거 | 축 충족률 · 순서 뒤집힘률 · 근거 대칭성 | 2순위 |
| 아젠다 선택셋 | 질의 100건 + 정답 `AgendaId` 조합 | 선택 정확도 | 3순위 |
| 성향 정합성 테스트 | Bull/Bear 고정, 성향만 바꿔 Judge 재실행 (메타모픽) | 사실 불변성 · 방향 단조성 · 판단 근거 연결률 | 3순위 |

### 핵심 지표

- **사실 정확도**: ≥ 80% — 골든셋 정답 수 / 전체
- **Bull 인용 반박률**: ≥ 70% — 유효한 bull_claim_ref 비율
- **아젠다 선택 정확도**: ≥ 80% — 질의 → AgendaId 매핑
- **거절 오답변율**: ≤ 5% — 답하면 안 되는데 답한 비율
- **사실 불변성**: ≥ 95% — 성향 바꿔도 verdict·stance 동일
- **방향 단조성 위반율**: ≤ 5% — 안정형에 더 공격적 강조 금지
- **판단 근거 연결률**: ≥ 90% — points_to_check ↔ evidence_ids
- **순서 뒤집힘률**: 측정 — A·B 순서 바꿨을 때 axis_verdict 변화
- **생성 지연 p95**: ≤ 180s — 단일 모드. 비교 모드는 실측 후
- **neutral 판정율**: 모니터링 — 0이면 판정 형식적 신호

## 흐름 · 전체 실행 흐름

*버튼 경로 기준. 채팅 경로는 precheck 뒤에 플래너가 계획을 1회 세우고 코드가 실행함.*

- `INPUT` **FE → `POST /orchestrate/debate`** — API가 세션에서 `user_id` 주입
- `관문1` **오케스트레이터 `resolve_entities`** — 애매하면 `clarification_needed`
- `precheck` **토론 에이전트 룰 판정** — reject면 즉시 `rejected` 반환 (T2는 수집 예약)
- `JOB` **job 생성(중복이면 기존 job 재사용) → 작업 큐 등록 → `job_started`** — precheck 결과를 큐 페이로드에 포함
- `워커` **`run_debate` 실행, 체크포인트 저장** — 진행 이벤트는 `job_events` → SSE
- `근거` **레지스트리 경유 조회** — `get_agent_context(ticker, "debate", query, intent)` · `get_metric(…, as_of)` · (플래그 켜짐) `get_ontology_context` 아젠다별 1회. 비교 모드는 축 단위 대칭 검색
- `토론` **Bull → Bear → Judge** — 단일: 조건부 2라운드 / 비교: 종목별 Bull·Bear 병렬 → Judge 축별 비교
- `검증` **L1 → 근거 부족 루프 → 1회 수정** — 실패 Claim은 제외하고 partial 고지
- `OUT` **`DebateResult` 저장 · 상태 전이** — 단일: `simulation_pending` (사용자가 `POST /orchestrate/debate/{job_id}/simulate`를 누르면 시뮬레이션 큐 등록, `sim_params` 없는 종목은 FE가 버튼 비활성화) / 비교: `debate_completed`

## 미결 · 미결 사항

*일정은 팀 협의 후 재확정. 아래는 담당과 결정이 필요한 내용만 기록.*

- **Q1** `ReasonCode`·`NextAction` 전체 이름 확정 → precheck·D4 대응표 채우기 — 미커버·3종목 이상·한쪽 미커버·데이터 부족 거절의 envelope.py 이름 확인 · 태은 + 유민
- **Q2** ~~SSE 이벤트 단위 — 토큰 vs 노드·주장 (수정 요청 1)~~ ✅ 해소 — ADR 0009(PR #43)·계약 draft.5(PR #46): 단계·주장 이벤트, `job_events` 1초 조회 → SSE · 태은
- **Q3** 배포 방식과 Lovable 구현 범위 재정의 — 최종본 7장은 상시 서버(Python API·워커) 권장. 백엔드가 Python·LangGraph라 Lovable 함수(BE)로 옮길 수 없으므로, 9/19 역할 분담의 "유민이 Lovable로 BE 구성"을 "Lovable로 FE 구성 + 상시 서버 API 연결"로 바꿀지 결정 필요 · 전원
- **Q4** 비교 모드 지연 목표·토큰 상한 — Langfuse 실측 후 · 유민
- **Q5** 조건부 2라운드 점수차 임계값 — 비용–품질 곡선 실측 후 · 유민
- **Q6** `stock_risk_grade`(사실 지표) 표시 주체 — 변동성 등 사실 지표로만 표시하기로 확정됨. `get_derived_snapshot` 값을 FE가 직접 쓸지, DebateResult에 넣을지 · 태은 + 수경
- **Q7** ~~`flow` 아젠다 활성화~~ ✅ 해소 — 수경 확인: `investor_flow_daily` T1 100종목 3년 치 적재. 키워드 사전 kw-0.1.1에서 활성화(PR #24) · 수경
- **Q8** 작업 큐 라이브러리 (PgQueuer vs Procrastinate) — 스파이크 후 결정. run_debate 체크포인트 연동 방식이 달라짐 · 태은
- **Q9** 공용 계약 패키지 위치 확정 — 최종본 8장 제안(backend/contracts + data-pipeline) 그대로 갈지 · 태은 + 수경

### v2.3 미결 중 종결된 것

| v2.3 | 결론 |
| --- | --- |
| Q2 온톨로지 구현체 | Supabase `ontology_nodes`·`ontology_edges` 원본, 메모리 로드, Phase B networkx, Neo4j는 전환 조건 충족 시 (5.2 Q9) |
| Q3 거절셋·기준선 실험 | 방식 확정(D10) → 구현 착수 시 작업 항목으로 전환 |
| Q5 Langfuse 실측 | Cloud Hobby, 태은 담당, 토론 종단 동작 시점에 측정 (5.2 Q6) |
| Q6 fire-and-forget | 작업 큐 + 체크포인트로 교체, 오케스트레이터가 기다리지 않는 성격은 유지 (5.2 Q10) |
| Q8 적합도 매트릭스 | label 미노출, 성향은 points_to_check·caution에만, 법률 검토 후 재검토 (5.2 Q14) |
| 보류 1 D3 | 이번 범위 포함. 종목마다 같은 축의 Bull·Bear를 따로 돌리고 Judge가 축별로 비교하는 구조(5.1)라 역할 붕괴 문제가 해소됨 (D3) |

### 구현 착수 시 유민 작업 항목

- **1**: `precheck()` + 키워드 사전 + `intent_data_sources.json` 연동 (오케스트레이터 관문1과 병렬 개발)
- **2**: 거절셋(`ReasonCode` 라벨) 수집 — precheck 구현 전에 먼저
- **3**: Bull·Bear·Judge 프롬프트 v3 + Pydantic 스키마 (단일 → 비교 순)
- **4**: 검증 레이어 L1 + 근거 부족 루프
- **5**: 기준선 비교 실험 루브릭 5~6항목 + 문항 30~50개
- **6**: 온톨로지 ISSUE 시드 20~30개 (온톨로지 기획서)

개미비서단 Agent F 리빌드 기획서 · v3.0 · 2026-10-21 · 이유민 · 멀티에이전트 설계 최종본(10/14) 반영
