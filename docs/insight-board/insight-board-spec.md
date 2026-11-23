# 인사이트보드(Agent E) 기획서

| 항목 | 값 |
| --- | --- |
| 버전 | **v2.2** (2026-11-24) |
| 상태 | 검토 중 |
| 담당 | 태은 |
| 계약 | [`openapi.yaml`](../api/openapi.yaml) `POST /orchestrate/insight-board`, `InsightBoardResult` |
| 구현 계획 | [`specs/001-orchestrator-trend-insight/`](../../specs/001-orchestrator-trend-insight/plan.md) |

## 변경 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1.0 | 2026-10-13 | Notion 아키텍처 초안 7.2 |
| v1.1 | 2026-11-05 | Notion 시그니처 계약 4장 (`CompanyData`·`Badge`·`Comment`) |
| v2.0 | 2026-11-23 | 저장소로 이관. SQLite 경로 제거(데이터 함수가 Supabase로 바뀜), 종목별 실패를 함수의 `error` 필드로 판정, 변동성 배지를 `get_derived_snapshot` 단일 정의로, 코멘트 요약·검증 규칙 확정 |
| v2.1 | 2026-11-23 | 실행 조건(1.1) 추가 — 오케스트레이터 기획서 v2.1 5.3 경로별 실행 조건 표와 연결 (#68 리뷰) |
| **v2.2** | 2026-11-24 | 데이터 조회를 도구 레지스트리 `invoke` 경유로 (오케스트레이터 기획서 v2.2 8장, 레지스트리 MVP 정정) |

### v1.1 → v2.0 무엇이 바뀌었나

| 항목 | v1.1 | v2.0 | 근거 |
| --- | --- | --- | --- |
| 데이터 접근 | `SQLiteDB` 인자 전달 | 인자 없이 호출. 데이터 함수가 Supabase에서 직접 읽고 `relational_db`는 무시함 | #35 |
| 종목별 부분 실패 | `gather(return_exceptions=True)` | 데이터 함수는 실패해도 예외를 던지지 않고 `error` 필드를 붙임 → **`error` 필드와 예외 둘 다** 실패로 판정 | 데이터 함수 동작 |
| 변동성 배지 | `volatility_30d` ≥ 0.03 (자리표시) | `get_derived_snapshot`의 `volatility_1m` ≥ `volatility_1m_market_threshold` | 데이터 함수 단일 정의 |
| 코멘트 입력 | 원본 JSON 전체 | 코드가 계산한 `FeatureSummary`만 | 토큰·숫자 환각 |
| 코멘트 검증 | 설계만 | 숫자 대조·금지 표현, 실패 시 빈 코멘트(fail-open 유지) | 헌법 원칙 IV |
| 응답 | `{raw_data, llm_comment, badges}` | 봉투 `InsightBoardEnvelope` + `InsightBoardResult` | 계약 |

## 1. 역할

선택한 종목 1-3개의 **주가·매크로·공시 데이터를 그대로 보여 주고**, 코드가 계산한 배지와 LLM 코멘트 1-2문장을 붙인다. 차트·표는 FE가 데이터로 그린다.

- 거절하지 않는다. 종목 확정 실패만 오케스트레이터 관문1이 거절한다.
- 일부 종목이 실패해도 나머지는 보여 준다(FN-CMN-01).

### 1.1 실행 조건

오케스트레이터 관문1이 `ROUTE_REQUIREMENTS[("insight_board", feature)]`로 종목마다 판정한다(오케스트레이터 기획서 5.3). 이 조건의 소유자는 이 문서다.

```python
("insight_board", "price"):      {"requires_any": ["price"]},
("insight_board", "disclosure"): {"requires_any": ["disclosure"]},
("insight_board", "macro"):      {"requires_any": []},   # 종목 데이터 불필요, 거절하지 않음
```

- 선택한 종목 중 하나라도 조건을 통과하지 못하면 관문1이 그 종목을 사유로 거절한다(대안 3개 포함). 사용자는 그 종목을 빼거나 바꿔 다시 요청한다.
- 조건을 통과한 뒤 조회에 실패한 종목은 거절이 아니라 `CompanyData.status="error"`로 처리한다(3장 ②). 조건 판정은 "데이터가 적재돼 있는가", 3장은 "이번 조회가 성공했는가"다.
- 조건을 바꾸면 오케스트레이터의 표와 이 절을 같은 PR에서 고친다.

## 2. 입력·출력

```python
async def run_insight_board(
    companies: list[CompanyContext],          # 1~3개
    feature: Literal["price", "macro", "disclosure"],
    date_from: str | None = None,
    date_to: str | None = None,
    as_of: str | None = None,                 # 없으면 today_kst()
) -> InsightBoardResult

class CompanyData(BaseModel):
    ticker: str; company: str
    status: Literal["ok", "empty", "error"]
    data: dict | None                         # 데이터 함수 반환값 그대로 (차트용)
    error: str | None = None                  # 함수의 error 코드 또는 예외 종류

class Badge(BaseModel):
    type: Literal["price_change", "volatility_high", "disclosure_count", "macro_direction"]
    ticker: str | None                        # 매크로는 None
    label: str                                # 화면 문구 (코드가 만듦)
    value: float | int | None
    direction: Literal["up", "down", "flat"] | None

class Comment(BaseModel):
    text: str                                 # 검증 실패·LLM 오류 시 ""
    verified: bool

class InsightBoardResult(BaseModel):
    status: Literal["ok", "partial"]
    feature: str
    items: list[CompanyData]
    badges: list[Badge]
    comment: Comment
    meta: ResponseMeta
```

## 3. 처리 단계

```text
① 조회      종목별 병렬 (asyncio.to_thread + gather(return_exceptions=True))
             price      get_price_data(ticker, date_from, date_to, as_of)
                        + get_derived_snapshot(ticker, as_of)   ← 변동성 배지용
             disclosure get_disclosure_data(ticker, date_from, date_to, as_of)
             macro      get_macro_data(date_from=…, date_to=…, as_of)  ← 종목과 무관, 1회
② 판정      예외 또는 error 필드 → error / 행 0개 → empty / 그 외 ok
③ 배지      compute_badges(feature, items)          코드
④ 요약      summarize_for_comment(feature, items)   코드
⑤ 코멘트    generate_comment(feature, summary)      LLM 1회
⑥ 검증      verify_comment(text, summary)           실패 시 text="" verified=false
⑦ status    error인 종목이 하나라도 있으면 partial (봉투 partial + retry_failed_parts[ticker])
             모든 종목이 error면 503 upstream_unavailable
```

- **조회 경로:** ①의 데이터 함수는 도구 레지스트리 `invoke(name, args, caller="insight_board")`로 부른다(오케스트레이터 기획서 8장). ②의 실패 판정은 `ToolResult.error`(함수의 `error` 필드를 레지스트리가 올린 값)와 예외로 한다.
- 매크로는 종목이 없으므로 `items`에 `ticker="macro"` 항목 하나만 둔다. 계약 `CompanyData.ticker`가 필수라서다.
- `meta.data_as_of`: 성공한 항목의 최신 데이터 날짜 중 가장 이른 날(서로 다른 기준일이면 보수적으로).

## 4. 배지 규칙 (코드)

| 기능 | 배지 | 규칙 |
| --- | --- | --- |
| price | `price_change` | 기간 첫 종가 대비 마지막 종가 변화율. `value`=소수(0.012), `direction` ±0.1% 안이면 flat, `label` "삼성전자 +1.2%" |
| price | `volatility_high` | `derived_snapshot.price_trend.volatility_1m` ≥ `volatility_1m_market_threshold`일 때만 |
| disclosure | `disclosure_count` | 기간 공시 건수. 0건이면 `label` "공시 없음" |
| macro | `macro_direction` | 지표별 최근값 vs 직전값, 같으면 flat |

- 퍼센트는 계산·저장 모두 소수, `label`에서만 %로 표시한다(코드 컨벤션).

## 5. 코멘트

### 5.1 요약 `summarize_for_comment`

LLM에는 아래 값만 넘긴다(원본 시계열을 넘기지 않음).

| 기능 | 요약 값 |
| --- | --- |
| price | 종목별 기간 변화율, 기간 최고·최저 종가와 날짜, 마지막 종가, 변동성 높음 여부 |
| disclosure | 종목별 건수, 유형별 건수(`disclosure_type`), 최신 공시 제목 3개 |
| macro | 지표별 최근값·직전값·변화 방향·기준일 |

### 5.2 생성·검증

- 프롬프트: "요약 값에 없는 숫자를 쓰지 않는다, 투자 권유 금지, 1~2문장". 모델 `INSIGHT_BOARD_LLM_MODEL`(기본 solar-mini).
- `verify_comment`:
  - 문장 속 숫자가 요약 값(표시 형식으로 반올림한 값 포함)에 있는가
  - 금지 표현(`backend/verification/text_rules.py`, 트렌드 리포트와 공용)
  - 실패하면 `text=""`, `verified=false`. 코멘트는 부가 정보라 요청 전체를 실패시키지 않는다(현행 fail-open 유지).
- `UPSTAGE_API_KEY`는 #60부터 필수라 키 없음 분기는 지운다.

## 6. 제거·변경하는 코드

| 파일 | 변경 |
| --- | --- |
| `data_client.py` | `_get_relational_db`·SQLite 제거, 종목별 실패 판정 추가 |
| `badges.py` | 문자열 → `Badge`, 변동성 기준 교체 |
| `comment_generator.py` | 입력을 `FeatureSummary`로, 검증 추가, 키 없음 분기 제거 |
| `config.py` | `load_dotenv` 제거(`core.config`가 담당) |
| `service.py` | 입력 `CompanyContext`, 반환 `InsightBoardResult` |

## 7. 평가 지표

| 지표 | 측정 | 목표 |
| --- | --- | --- |
| 부분 실패 노출 | 한 종목 실패 시 나머지 종목 노출 | 100% (자동 테스트) |
| 코멘트 검증 통과율 | `verified=true` 비율 | 기준선 측정 후 |
| 코멘트 숫자 불일치 | 노출 코멘트 중 | 0건 |
| 응답 지연 | p95 | 기준선 측정 후 (목표 3초) |

## 8. 미결 사항

| # | 내용 | 상대 |
| --- | --- | --- |
| Q1 | 매크로 항목의 `ticker` 표기 (`"macro"`) — 계약에 명시 필요 | 계약 PR |
| Q2 | feature 확장(financials·flow·market) 1차 포함 여부 | 팀 (기본: 미포함) |
| Q3 | `get_price_data`가 `date.today()` 상한을 씀 → `as_of` 명시 호출로 회피 (#55) | 수경 |
