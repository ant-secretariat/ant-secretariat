# get_metric 반환 형식

`get_metric(ticker, metric_id, as_of)`는 시맨틱 레이어의 단일 정의로 지표 하나를 계산합니다. 반환 형식은 API 계약서(`docs/api/openapi.yaml`)의 `MetricValue`이고, 계약서 필드는 그대로 두고 필드를 덧붙였습니다. 이 문서가 데이터 에이전트 쪽 확정 형식입니다(2026-11-10).

```python
from processing.functions.get_metric import get_metric

get_metric("000660", "foreign_net_buy_20d", "2026-11-10")
```

```json
{
  "ticker": "000660",
  "metric_id": "foreign_net_buy_20d",
  "value": -11690952418000.0,
  "unit": "원",
  "basis": "최근 20거래일 합계",
  "as_of": "2026-11-06",
  "source": ["investor_flow_daily"],
  "reason": null,
  "requested_as_of": "2026-11-10",
  "display": "-11.69조 원"
}
```

## 필드

| 필드 | 계약서 | 뜻 |
| --- | --- | --- |
| `ticker`, `metric_id` | O | 요청한 종목·지표 |
| `value` | O | 숫자(float) 또는 `null`. **%는 퍼센트 숫자**입니다(76.33 = 76.33%, 비율 0.7633 아님). 금액은 원 단위 그대로 |
| `unit` | O | 아래 6개 중 하나. 알 수 없는 지표면 빈 문자열 |
| `basis` | O | 계산 기준 설명(예: "2026Q2 연결, 전년 동기 대비", "최근 20거래일 합계") |
| `as_of` | O | **실제로 쓴 데이터의 날짜**. 시세·수급은 거래일, 재무는 공시 접수일, 지분공시는 마지막 보고 접수일. 값이 없으면 요청한 날 |
| `source` | O | 계산에 쓴 Supabase 표 목록 |
| `reason` | O | `value`가 `null`인 사유(아래 5개). 값이 있으면 `null` |
| `requested_as_of` | 추가 | 요청한 날. `as_of`와 비교하면 데이터가 며칠 전 것인지 알 수 있음 |
| `display` | 추가 | 문장에 그대로 넣을 표시용 문자열. `value`가 `null`이면 `null` |
| `period` | 추가 | 재무 지표만. 계산에 쓴 분기(예: `2026Q2`) |

## unit (6개)

`배`, `원`, `%`, `%p`, `주`, `건`

## reason (5개)

| 코드 | 뜻 | 토론·트렌드 리포트 처리 제안 |
| --- | --- | --- |
| `unknown_metric` | `metric_id`가 목록에 없음 | 프롬프트·코드의 지표 이름 오류 |
| `metric_unavailable` | DB 조회 실패(일시적) | 다시 시도하거나 숫자 없이 서술 |
| `no_data` | 그날까지 이 종목의 데이터가 없음(적재 범위 밖 포함) | 숫자 없이 서술하거나 그 주장 제외 |
| `no_value` | 데이터 행은 있지만 이 지표 값이 비어 있음(예: 적자라 PER 없음, 금융업이라 매출 없음) | 숫자 없이 서술 |
| `not_applicable_financials` | 금융업이라 의미 없는 지표(부채비율) | 그 지표 대신 다른 지표 사용 |

## display 규칙

| unit | 규칙 | 예 |
| --- | --- | --- |
| `배`, `%`, `%p` | 소수 둘째 자리까지(끝의 0은 지움) | `18.25배`, `0.9배`, `76.33%`, `0%p` |
| `원` (주당 값: `close`, `eps`, `bps`, `dps`) | 쉼표 정수 | `1,176,000원` |
| `원` (합계 금액) | 1조 이상은 조 원, 1억 이상은 억 원, 그 미만은 쉼표 정수 | `826.92조 원`, `-3,152.6억 원` |
| `주`, `건` | 쉼표 정수 | `730,492,365주`, `3건` |

증감을 나타내는 지표(`foreign_net_buy_20d`, `inst_net_buy_20d`, `individual_net_buy_20d`, `revenue_growth_yoy`, `insider_net_shares_90d`, `major_holder_ratio_change_90d`)는 양수에 `+`를 붙입니다.

## 플레이스홀더 치환 (토론 검증 레이어와의 약속)

- 문장에는 `{{metric_id}}`(단일 종목) 또는 `{{종목코드.metric_id}}`(비교 모드)로 적고, `get_metric` 결과의 `display`로 바꿉니다
- `display`가 `null`이면(값 없음) 그 자리를 숫자로 채우지 말고 주장을 다시 쓰거나 뺍니다
- 지표 이름이 헷갈릴 때는 `find_terms`(용어 → `metric_id`, 예: "영업이익률" → `operating_margin`)를 씁니다

## metric_id (22개)

| 묶음 | metric_id |
| --- | --- |
| 시세·밸류에이션 (10) | `per`, `pbr`, `eps`, `bps`, `dividend_yield`, `dps`, `foreign_ratio`, `shares_outstanding`, `close`, `market_cap` |
| 재무 (4) | `debt_ratio`, `operating_margin`, `revenue_growth_yoy`, `roe_ttm` |
| 수급 (5) | `foreign_net_buy_20d`, `inst_net_buy_20d`, `individual_net_buy_20d`, `short_volume_ratio_20d`, `short_balance_ratio` |
| 지분공시 (3) | `insider_net_shares_90d`, `insider_sell_reports_90d`, `major_holder_ratio_change_90d` |
