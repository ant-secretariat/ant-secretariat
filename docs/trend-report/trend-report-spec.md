# 트렌드 리포트(Agent D) 기획서

| 항목 | 값 |
| --- | --- |
| 버전 | **v2.1** (2026-11-23) |
| 상태 | 검토 중 |
| 담당 | 태은 |
| 기능 ID | FN-TR-01 (카드 생성), FN-TR-02 (근거 연결) |
| 계약 | [`openapi.yaml`](../api/openapi.yaml) `POST /orchestrate/trend-report`, `TrendReportResult` |
| 관련 결정 | ADR 0005 (pgvector), ADR 0006 (DataTier), ADR 0010 (컨센서스 180일) |
| 구현 계획 | [`specs/001-orchestrator-trend-insight/`](../../specs/001-orchestrator-trend-insight/plan.md) |

## 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1.0 | 2026-10-13 | Notion 아키텍처 초안 7.1 (절차형 단계 + 근거 부족 루프) |
| v1.1 | 2026-11-05 | Notion 시그니처 계약 3장 (`select_evidence` 등 5단계, `TrendCards`) |
| v2.0 | 2026-11-23 | 저장소로 이관. Pinecone·SQLite 경로 제거, `get_agent_context`·컨센서스(ADR 0010) 기준으로 수정, 목표주가 방향 계산 규칙·`BrokerView`·`verification` 정의, 근거 부족 루프를 S1~S3로 한정 |
| **v2.1** | 2026-11-23 | 실행 조건(1.1) 추가 — 오케스트레이터 기획서 v2.1 5.3 경로별 실행 조건 표와 연결 (#68 리뷰) |

### v1.1 → v2.0 무엇이 바뀌었나

| 항목 | v1.1 | v2.0 | 근거 |
| --- | --- | --- | --- |
| 데이터 경로 | `DataAgentClient`(SQLite+Pinecone) 또는 `get_agent_context` 검토 | **`get_agent_context(ticker, "trend_report", query, intent)`** 하나로. Pinecone 키 요구 제거 | ADR 0005, #53 |
| `data_tier` | 신규 필드 | `get_agent_context`가 돌려줌(#53). 머지 전에는 `data_tier_for()`로 계산 | #53, ADR 0006 |
| 목표주가 | `consensus` 키로 매핑 | **`consensus`(최근 180일, 증권사별 최신 1건)** 사용, 방향은 아래 4.2 규칙으로 코드가 계산 | ADR 0010 |
| 매크로 문서 | `"macro_summary"` 확인 필요 | `document_chunks.document_type`은 `macro`. 별칭으로 동작하지만 `"macro"`로 직접 호출 | 마이그레이션 `document_chunks` |
| 레거시 경로 | `run()`·`ReportRetriever` 제거 | 제거 확정 (`run.py`, `pinecone_retriever.py`, `CompanyEvidence` 포함) | ADR 0005 |
| 근거 부족 루프 | S1~S5 | **MVP는 S1~S3**(LLM 없는 규칙). S4~S5는 Post-MVP | 10초 목표, 비용 |
| `BrokerView`·`verification` | 미정의 | 4.3·5.3에서 정의, 계약에 추가 | 계약 미정의 |
| 응답 | `{report: ...}` | 공통 봉투 `TrendReportEnvelope`. `/agents/trend-report`는 FE 전환까지 병행 | 계약 |

## 1. 역할

종목 하나에 대해 **증권사 리포트·뉴스·공시·매크로 근거로 카드 6종을 만든다.** 숫자와 방향은 코드가 계산하고, LLM은 근거에 붙은 설명 문장만 쓴다. 모든 주장에는 근거 ID가 있다.

- 목표 지연: p95 ≤ 10초 (FN-TR-01)
- 투자 권유 표현 0건, 근거 없는 주장 0건 노출 (헌법 원칙 IV)

### 1.1 실행 조건

오케스트레이터 관문1이 `ROUTE_REQUIREMENTS[("trend_report", None)]`로 판정한다(오케스트레이터 기획서 5.3). 이 조건의 소유자는 이 문서다.

```python
("trend_report", None): {"requires_any": ["report", "news", "disclosure", "derived"]}
```

- 하나도 없으면(`macro_only`) 관문1에서 rejected `no_data`로 끝나고 이 에이전트는 호출되지 않는다. 7장의 `macro_only` 행은 관문1을 거치지 않는 호출(테스트·배치)을 위한 방어다.
- 조건을 바꾸면 오케스트레이터의 표와 이 절을 같은 PR에서 고친다.

## 2. 입력

```python
@dataclass(frozen=True)
class TrendReportRequest:
    ticker: str
    company: str
    sector: str = ""
    tier: Tier = Tier.T1
    query: str | None = None             # 없으면 기본 질의 "{company} {sector} 실적 전망 …"
    intent: list[AgendaId] | None = None # get_agent_context에 그대로 전달
    date_from: str | None = None
    date_to: str | None = None
    as_of_date: str | None = None        # 없으면 today_kst()
```

- `as_of_date`는 모든 데이터 조회의 상한이다. `as_of` 이후에 발표된 문서·목표가는 쓰지 않는다(헌법 원칙 III, look-ahead 금지).

## 3. 처리 단계

```text
① 데이터 조회   get_agent_context(ticker, "trend_report", query, intent)   [수경 #53]
                 → report/news/macro 문서, target_prices, price_data, macro_data, data_tier
                 + get_disclosure_data(ticker, date_from, date_to, as_of)  (공시 카드 근거)
② 근거 선택     select_evidence()       코드: 중복 제거·관련도 컷·최신순·종류별 상한 → Evidence[S1..Sn]
③ 숫자 계산     compute_target_price_trend()  코드: consensus·방향 (4.2)
④ 카드 생성     generate_cards()        LLM 1회, JSON 스키마 강제, 주장마다 evidence_ids
⑤ 검증         verify_cards()          L1: 인용 존재·금지 표현·숫자 대조·자리표시 잔여
⑥ 보완         fill_card_gaps()        실패한 주장만 S1~S3 (카드당 2회, 전체 +3초)
⑦ 정리         실패한 주장 철회 → data_tier 카드 정책 적용 → status 결정 → 봉투
```

### 3.1 근거 선택 `select_evidence`

| 규칙 | 값 | 이유 |
| --- | --- | --- |
| 중복 제거 | 같은 `report_id`(문서)에서 최대 2청크 | 한 리포트가 근거를 독점하지 않게 |
| 관련도 | 하이브리드 점수 하위 청크 제외(RRF 순위 상위 N만) | 무관한 청크로 LLM이 지어내지 않게 |
| 상한 | 리포트 5 · 뉴스 4 · 공시 3 · 매크로 2 | 현재 `ReportGenerator` 상한 유지 + 공시 추가 |
| 정렬 | 종류별로 최신순 | 카드는 최근 흐름을 말함 |
| 미리보기 | `content_preview` 240자 | 계약 Evidence |

- 정형 데이터(목표주가·시세·매크로 지표)는 `document_type="structured"` 근거로 1개씩 넣는다. 목표주가 근거는 특정 리포트가 아니라 KIS 집계라 리포트 ID를 붙이지 않는다.

### 3.2 카드 생성 `generate_cards`

- 프롬프트에 근거 목록(`[S1] 날짜 | 출처 | 제목 | 본문 일부`)과 ③의 계산 결과만 넣는다. 원본 컨텍스트 전체를 넣지 않는다(현재는 `price_data`·`macro_data` 원본을 통째로 넣음).
- 출력은 Pydantic 스키마(`TrendCardsDraft`)로 강제한다. Solar의 JSON 모드를 쓰고, 파싱 실패 시 1회 재요청, 그래도 실패하면 `status=empty` + `partial_result`가 아니라 503 `upstream_unavailable`.
- 숫자는 LLM이 근거 문장에서 인용한 값만 쓸 수 있다. 목표주가 평균·최고·최저는 LLM 출력에 넣지 않고 코드 값으로 채운다.

## 4. 출력

### 4.1 카드

```python
class TrendCards(BaseModel):
    summary: list[Claim]              # 핵심 2~3개
    positive_factors: list[Claim]
    risk_factors: list[Claim]
    broker_differences: list[BrokerView]
    target_price_trend: TargetPriceTrend
    news_issue_cards: list[Claim]
    macro_comment: Claim | None

class Claim(BaseModel):              # 계약 Claim (토론과 공용)
    claim_id: str
    text: str
    claim_type: Literal["numeric", "event", "opinion", "table"]
    evidence_ids: list[str]           # 최소 1개. 비면 검증 실패
```

### 4.2 목표주가 방향 `compute_target_price_trend` (코드)

`get_target_price_data(ticker, as_of=as_of_date)`의 `consensus`(ADR 0010: 최근 180일, 증권사별 최신 1건)와 `records`로 계산한다.

| 방향 | 규칙 |
| --- | --- |
| `근거 부족` | `broker_count` < 2 |
| `상향` | 최근 90일 안에 목표가를 바꾼 증권사 중 올린 곳이 2/3 이상, 또는 현재 평균이 90일 전 평균보다 +3% 이상 |
| `하향` | 위와 반대 |
| `혼조` | 최근 90일 변경이 있지만 올림·내림 어느 쪽도 2/3 미만 |
| `유지` | 최근 90일 안에 목표가를 바꾼 증권사가 없음, 또는 평균 변화가 ±3% 안 |

- 90일 전 평균은 같은 함수를 `as_of = as_of_date - 90일`로 한 번 더 불러 구한다.
- 임계값(2/3, 3%, 90일)은 운영 DB 분포를 보고 확정한다(research R5). `comment`만 LLM이 쓴다.

### 4.3 증권사 시각차 `BrokerView` (계약에 추가)

```python
class BrokerView(BaseModel):
    broker: str                       # 증권사명 (mbcr_name)
    opinion: Literal["매수", "중립", "매도"] | None   # 코드: opinion_norm
    target_price: int | None          # 코드: 분할 환산 목표가
    published_at: str                 # 코드
    view: Claim                       # LLM: 그 증권사 리포트 근거로 한 문장
```

- 목표가가 컨센서스 평균에서 가장 먼 증권사 위·아래 1곳씩(최대 2개)을 코드가 고르고, 그 증권사의 리포트 청크가 근거에 있을 때만 LLM이 `view`를 쓴다. 없으면 카드에서 뺀다.

### 4.4 결과

```python
class TrendReportResult(BaseModel):
    status: Literal["ok", "partial", "empty"]
    ticker: str; company: str; as_of_date: str
    data_tier: DataTier
    cards: TrendCards
    evidence: list[Evidence]
    data_status: DataStatus           # get_available_data_status 결과 그대로
    verification: VerificationSummary
    meta: ResponseMeta                # prompt_version, model, data_as_of, trace_id
```

- **`status` 규칙 (FN-TR-01):** 요약과 리스크가 모두 비면 `ok`가 될 수 없다. 둘 다 비면 `empty`, 일부 카드만 철회됐으면 `partial`(봉투도 `partial` + `retry_failed_parts`).
- **`meta.data_as_of`:** 쓰인 근거·정형 데이터 중 가장 최근 날짜.

## 5. 검증과 보완

### 5.1 L1 검사 `verify_cards`

| 검사 | 실패 조건 |
| --- | --- |
| `citation` | `evidence_ids`가 비었거나, 선택된 근거에 없는 ID |
| `forbidden` | 투자 권유·단정 표현 (토론 L1의 `find_forbidden` 공용화, 6장) |
| `number` | 문장 속 숫자가 인용한 근거 본문·정형 값에 없음 (단위 환산·반올림 허용 오차 1%) |
| `placeholder` | `{{…}}` 잔여 |
| `freshness` | 인용 근거가 모두 `as_of_date` 기준 180일보다 오래됨 → 실패가 아니라 문장 끝에 기준일 표시 |

### 5.2 근거 부족 보완 `fill_card_gaps` (MVP: S1~S3)

`citation`·`number`로 실패한 주장만 대상이다. 같은 입력은 같은 결과를 내므로 **실패할 때마다 입력을 바꾼다.**

| 단계 | 바꾸는 것 | LLM |
| --- | --- | --- |
| S1 기간 확대 | `date_from` 30 → 90 → 180일 | 없음 |
| S2 유형 전환 | report → news → disclosure | 없음 |
| S3 도구 전환 | `numeric`은 `get_financials`·`get_derived_snapshot`, `table`은 `chunk_type='table'` | 없음 |

- 새 청크가 0개면 다음 단계로, 연속 2회 0개면 종료. 이미 시도한 `(함수, 인자)`는 다시 부르지 않는다.
- 예산: 카드당 2회, 리포트 전체 +3초. 먼저 소진되는 쪽에서 멈춘다.
- 새 근거를 찾으면 주장의 `evidence_ids`에 붙이고 `evidence_source="gap_fill"`로 표시한다. 근거가 주장을 뒷받침하는지(L2)는 MVP에서 판정하지 않으므로, **보완된 주장은 재생성하지 않고 숫자·인용 검사만 다시 한다.** 다시 실패하면 철회한다.
- 철회·보완 결과는 `verification`과 로그로 남긴다. `evidence_gap_log` 테이블은 Post-MVP.

### 5.3 `VerificationSummary` (계약에 추가)

```python
class VerificationSummary(BaseModel):
    checked: int          # 검사한 주장 수
    retracted: int        # 철회한 주장 수
    gap_filled: int       # 보완 근거로 통과한 주장 수
    failed_checks: dict[str, int]   # 검사 종류별 실패 수 (citation·number·forbidden·placeholder)
```

## 6. 공통 검증 모듈

- 토론 L1(`agents/debate_renewal/validation/l1.py`)의 금지 표현·자리표시 규칙을 `backend/verification/text_rules.py`로 옮겨 트렌드 리포트·인사이트보드·토론이 같이 쓴다. 토론 쪽은 import만 바꾼다(유민 리뷰).
- 트렌드 리포트 전용 검사(인용·숫자 대조)는 `agents/trend_report/verify.py`에 둔다.

## 7. data_tier별 카드 정책

| `data_tier` | 노출 카드 | 숨김 카드 |
| --- | --- | --- |
| `report` | 전체 | — |
| `news_only`, `disclosure_only` | 요약·긍정·리스크·뉴스 이슈·목표주가(KIS 값이 있을 때) | 증권사 시각차 |
| `derived_only` | 요약(정량)·리스크(변동성·밸류에이션 위치) + "심층 분석 준비 중" 고지 | 증권사 시각차·뉴스 이슈 |
| `macro_only` | 없음 → `status=empty`, 봉투 `rejected` `no_data` | 전체 |

## 8. 제거하는 코드

| 파일 | 이유 |
| --- | --- |
| `pinecone_retriever.py`, `run.py`, `TrendReportAgent.run()`, `CompanyEvidence`·`ReportChunk` | Pinecone 직접 호출 레거시 (ADR 0005) |
| `data_agent_client.py` | `get_agent_context`로 대체 |
| `config.SUPPORTED_COMPANIES`·`DEFAULT_TICKERS` | 종목은 `companies` 테이블 (관문1) |
| `_patch_target_price_summary` | 목표주가를 처음부터 코드가 계산 |
| `config.today_kst`·`require_env` | `crawling.config.clock.today_kst`, `core.config` |

## 9. 평가 지표

| 지표 | 측정 | 목표 |
| --- | --- | --- |
| 근거 연결률 | 노출된 주장 중 L1 인용 검사 통과 비율 | 100% (철회로 보장) |
| 숫자 불일치 | 화면 숫자 vs 원천 데이터 | 0건 |
| 철회율 | 생성 주장 중 철회 비율 | 기준선 측정 후 (높으면 데이터 커버리지 문제) |
| 생성 지연 | p95 | ≤ 10초 |
| 금지 표현 | 노출 문장 중 | 0건 |

## 10. 미결 사항

| # | 내용 | 상대 |
| --- | --- | --- |
| Q1 | #53 머지 시점 (`data_tier`, `intent`). 그 전에는 `data_tier_for()`로 계산 | 수경 |
| Q2 | 목표주가 방향 임계값 (2/3, 3%, 90일) | 운영 DB 확인 |
| Q3 | `macro` 문서가 `document_chunks`에 실제로 있는지, 없으면 매크로 카드는 `get_macro_data` 정형 값만 | 수경 |
| Q4 | 데이터 함수 일부가 `date.today()` 기본값 → `as_of`를 항상 명시해서 호출 (#55) | 수경 |
| Q5 | `BrokerView`·`VerificationSummary` 계약 추가 | 계약 PR |
