# 트렌드 리포트(Agent D) 기획서

| 항목 | 값 |
| --- | --- |
| 버전 | **v2.3** (2026-11-24) |
| 상태 | 검토 중 |
| 담당 | 태은 |
| 기능 ID | FN-TR-01 (카드 생성), FN-TR-02 (근거 연결) |
| 계약 | [`openapi.yaml`](../api/openapi.yaml) `POST /orchestrate/trend-report`, `TrendReportResult` |
| 관련 결정 | ADR 0005 (pgvector), ADR 0006 (DataTier), ADR 0010 (컨센서스 180일) |
| 후속 이슈 | #81 근거 개수 실험, #82 목표주가 방향 경계값 |
| 구현 계획 | [`specs/001-orchestrator-trend-insight/`](../../specs/001-orchestrator-trend-insight/plan.md) |

## 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1.0 | 2026-10-13 | Notion 아키텍처 초안 7.1 (절차형 단계 + 근거 부족 루프) |
| v1.1 | 2026-11-05 | Notion 시그니처 계약 3장 (`select_evidence` 등 5단계, `TrendCards`) |
| v2.0 | 2026-11-23 | 저장소로 이관. Pinecone·SQLite 경로 제거, `get_agent_context`·컨센서스(ADR 0010) 기준으로 수정, 목표주가 방향 계산 규칙·`BrokerView`·`verification` 정의, 근거 부족 루프를 S1~S3로 한정 |
| v2.1 | 2026-11-23 | 실행 조건(1.1) 추가 — 오케스트레이터 기획서 v2.1 5.3 경로별 실행 조건 표와 연결 (#68 리뷰) |
| v2.2 | 2026-11-24 | #69 리뷰 반영: `intent`를 단일 값으로, `as_of`를 각 함수에 직접 전달, 근거 개수는 초기값(#81), 매크로 문서 0건 → 정형 값만, 증권사 이름은 `broker_key`로 매칭, **목표주가 방향을 개정 비율 방식으로 교체**(#82), 변동성 표기 |
| **v2.3** | 2026-11-24 | 데이터 조회를 도구 레지스트리 `invoke` 경유로 (오케스트레이터 기획서 v2.2 8장, 레지스트리 MVP 정정) |

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
    intent: AgendaId | None = None       # 질문 주제(아젠다) 하나. 버튼 경로는 보통 None
    date_from: str | None = None
    date_to: str | None = None
    as_of_date: str | None = None        # 없으면 today_kst()
```

- `as_of_date`는 모든 데이터 조회의 상한이다. `as_of` 이후에 발표된 문서·목표가는 쓰지 않는다(헌법 원칙 III, look-ahead 금지).
- `intent`는 **AgendaId**(질문이 묻는 주제: `valuation`·`macro`·`risk`·`growth`·`shareholder_return`·`flow`)다. 에이전트 종류는 `get_agent_context`의 `agent_type="trend_report"`가 따로 맡는다. 데이터 함수(#53)와 계약이 값 하나만 받으므로 리스트로 두지 않는다.

## 3. 처리 단계

```text
① 데이터 조회   get_agent_context(ticker, "trend_report", query, intent, as_of)   [수경 #53, as_of 추가 예정]
                 → report/news 문서, target_prices, price_data, macro_data, data_tier
                 + get_disclosure_data(ticker, date_from, date_to, as_of)  (공시 카드 근거)
② 근거 선택     select_evidence()       코드: 중복 제거·관련도 컷·최신순·종류별 상한 → Evidence[S1..Sn]
③ 숫자 계산     compute_target_price_trend()  코드: consensus·방향 (4.2)
④ 카드 생성     generate_cards()        LLM 1회, JSON 스키마 강제, 주장마다 evidence_ids
⑤ 검증         verify_cards()          L1: 인용 존재·금지 표현·숫자 대조·자리표시 잔여
⑥ 보완         fill_card_gaps()        실패한 주장만 S1~S3 (카드당 2회, 전체 +3초)
⑦ 정리         실패한 주장 철회 → data_tier 카드 정책 적용 → status 결정 → 봉투
```

- **`as_of` 전달:** `get_agent_context`에 `as_of`가 추가되기 전까지는(수경 작업 중) 검색·목표주가를 `search_documents(as_of=)`·`get_target_price_data(as_of=)`로 직접 부른다. 과거 날짜 리포트에 그 뒤 문서가 섞이지 않게 하기 위해서다.
- **매크로:** `document_chunks`에 매크로 문서가 0건이다(11/23). 매크로 카드는 `get_macro_data` 정형 값만으로 만들고, 매크로 문서 검색은 하지 않는다.

- **조회 경로:** ①의 모든 데이터 함수는 도구 레지스트리 `invoke(name, args, caller="trend_report")`로 부른다(오케스트레이터 기획서 8장). 직접 import하지 않는다. 조회 실패는 `ToolResult.error`로 받아 "데이터 없음"과 구분한다.

### 3.1 근거 선택 `select_evidence`

| 규칙 | 값 | 이유 |
| --- | --- | --- |
| 중복 제거 | 같은 `doc_id`(문서)에서 최대 2청크 | 한 리포트가 근거를 독점하지 않게. `doc_id`는 검색 결과에 추가 예정(수경) |
| 관련도 | 하이브리드 점수 하위 청크 제외(RRF 순위 상위 N만) | 무관한 청크로 LLM이 지어내지 않게 |
| 후보 | 데이터 쪽에서 종류당 약 15개 (`top_k` 조정, 수경) | 줄이는 일은 이 함수가 함 |
| 상한 | **초기값** 리포트 5 · 뉴스 4 · 공시 3 | 기존 `ReportGenerator` 상수를 옮긴 값. **#81 실험으로 확정** |
| 정렬 | 종류별로 최신순 | 카드는 최근 흐름을 말함 |
| 미리보기 | `content_preview` 240자 | 계약 Evidence |

- 상한을 두는 이유: 10초 지연 목표, 토큰 비용, 그리고 근거가 많을수록 중간 근거를 덜 보고 근거와 무관한 문장을 쓸 여지가 커진다. 방식(넉넉히 받고 줄이기)은 확정이고 숫자만 #81에서 정한다.
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

### 4.2 목표주가 수준과 방향 `compute_target_price_trend` (코드)

수준과 방향을 나눠서 계산한다. LLM은 `comment`만 쓴다.

| 구분 | 지표 | 계산 | 근거 |
| --- | --- | --- | --- |
| **수준** (지금 얼마인가) | 평균·최고·최저 목표가, 증권사 수 | `get_target_price_data(ticker, as_of)`의 `consensus` (증권사별 최신 1건, 최근 180일) | ADR 0010. 국내 컨센서스(에프앤가이드)도 증권사 목표가의 단순 평균 |
| **방향** (올라가는 중인가) | 상향·하향·유지 개정 수, 상향 비율 r | 같은 증권사의 **직전 → 최신 목표가** 쌍을 최근 3개월 안에서 센다. r = 상향 ÷ (상향 + 하향) | LSEG Revision Ratio(상향 ÷ 전체 개정), BofA 3개월 이동 상향/하향 비율. 목표주가 개정은 시장에 정보가 있다(Asquith·Mikhail·Au 2005) |

- **평균 차이로 방향을 정하지 않는다.** 90일 전 평균과 지금 평균은 포함된 증권사가 달라서(180일 창에서 빠지거나 새로 들어온 증권사), 차이가 의견 변화가 아니라 구성 변화일 수 있다(#69 리뷰). 평균 변화는 화면 표시용으로만 쓴다.
- **분류는 한 규칙으로만 한다** (규칙이 겹쳐 상향·하향이 동시에 되는 문제 제거).

| 방향 | 조건 (경계값은 #82에서 확정, 아래는 초기값) |
| --- | --- |
| `근거 부족` | 컨센서스 증권사 3곳 미만 (에프앤가이드도 3곳 이상일 때만 컨센서스 산출) |
| `유지` | 최근 3개월 안에 개정한 증권사가 없음, 또는 개정이 모두 같은 가격 |
| `상향` | r ≥ 2/3 |
| `하향` | r ≤ 1/3 |
| `혼조` | 그 사이 |

- **화면에는 숫자를 같이 보인다:** "최근 3개월 목표가 상향 5곳 · 하향 1곳 · 평균 OO원". 라벨만 보여 줄 때보다 해석 논쟁이 적고 근거로 바로 이어진다.
- **계산 위치 (제안):** 토론도 같은 규칙을 쓴다(#69 리뷰). 개정 집계(건수·증권사별 변화율)는 데이터 쪽 `get_target_price_data` 결과의 `revisions`로 두고, 라벨 경계값만 이 함수가 적용하는 안을 수경과 협의한다(#82). 정해지기 전까지는 `records`에서 직접 센다.

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
- **증권사 매칭은 `broker_key`로 한다.** KIS 목표가(`키움`, `NH투자`)와 리포트(`키움증권`)의 표기가 달라 그대로 맞으면 2곳뿐이다(11/23). 데이터 쪽이 목표가 `records`와 검색 결과에 같은 `broker_key`를 넣는다(수경).
  - 만드는 방식: 공백·`(주)`·"증권"·"투자증권" 같은 접미어를 지우는 정규화 규칙 + 그래도 안 맞는 경우만 정적 예외 사전(기준 키 → 별칭, 적용 기간. 예: 이베스트투자증권 → LS증권).
  - 실시간 LLM 매핑은 쓰지 않는다(정해진 30곳 안팎의 집합이라 비용·지연만 늘고 결과가 결정적이지 않음). 초안은 LLM으로 만들 수 있지만 사람이 검수해 파일로 커밋한다.
  - DB의 모든 증권사 이름이 기준 키로 매핑되는지 테스트로 확인해 새 이름이 들어와도 놓치지 않는다.

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
| S3 도구 전환 | `numeric`은 `get_financials`·`get_derived_snapshot`, `table`은 표 조각(`chunk_type='table'`, 12,714개. `search_documents`에 거르는 인자 추가 필요, 수경) | 없음 |

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

- 리스크 카드의 변동성은 `get_derived_snapshot`의 실현 변동성이다. 시뮬레이션(GARCH 추정)과 값이 달라 보일 수 있어 "최근 3개월 실현 변동성"처럼 이름을 붙인다(#69 리뷰).
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
| ~~Q1~~ | #53 머지 시점 → **해결:** 11/23 머지, `data_tier`·`intent` 바로 사용 | 수경 |
| Q2 | 목표주가 방향 경계값 → 개정 비율 방식으로 바꾸고 경계값은 #82 | 운영 DB |
| ~~Q3~~ | 매크로 문서 → **해결:** 0건, 매크로 카드는 정형 값만 | 수경 |
| Q4 | 데이터 함수 일부가 `date.today()` 기본값 → `as_of`를 항상 명시해서 호출 (#55) | 수경 |
| Q5 | `BrokerView`·`VerificationSummary` 계약 추가 | 계약 PR |
| Q6 | 근거 개수 상한 실험 | #81 |
| Q7 | 데이터 쪽 추가: `get_agent_context(as_of=)`, 후보 `top_k`, 검색 결과 `doc_id`·`broker_key`, `search_documents` 표 조각 필터, `revisions` | 수경 |
