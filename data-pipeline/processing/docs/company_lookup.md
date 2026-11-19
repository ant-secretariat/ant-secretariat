# 종목 찾기 함수

`resolve_company`, `search_companies`, `extract_company_mentions`, `find_terms`. 반환 형식은 API 계약서(`docs/api/openapi.yaml`)의 `ResolvedCompany`, `SearchCompaniesOutput`(`Candidate` 목록), `ExtractCompanyMentionsOutput`을 따릅니다.

- 종목 목록(정식명·종목코드·WICS 업종·티어·시가총액)은 Supabase `companies`에서 읽어 10분 동안 메모리에 둡니다(`SUPABASE_DB_URL` 필요). 예전 고정 목록(`processing/config/supported_companies.py`)은 쓰지 않습니다
- 별칭·업종 용어·지표 용어는 `processing/config/company_terms.json`(코드로 관리하는 사전)에 있습니다. DB 표가 아니라서 사전을 고쳐도 마이그레이션이 필요 없습니다
- 시가총액은 시세가 적재된 종목(현재 T1 100개)만 있고, 나머지는 `null`이라 같은 그룹 안에서 뒤로 갑니다

## 찾는 순서

| 순서 | 종류(`match`) | 예 | 자동 확정 |
| --- | --- | --- | --- |
| 1 | `ticker` 종목코드 | `005930` | O |
| 2 | `name` 정식명 (공백·대소문자·`(주)` 무시) | `삼성 전자`, `naver` | O |
| 3 | `alias` 별칭 | `삼전`, `하이닉스`, `LG엔솔` | O |
| 4 | `group` 그룹 별칭 | `삼성`, `엘지`, `현대` | X (후보) |
| 5 | `prefix` 접두어 | `삼성바` → 삼성바이오로직스 | X (후보) |
| 6 | `chosung` 초성 | `ㅅㅅㅈㅈ`, `ㅎㄷ` | X (후보) |

같은 순서 안에서는 시가총액이 큰 종목이 먼저고, 보통주가 우선주보다 앞입니다. 유사도 점수로 추측하지 않습니다.

## resolve_company(company_input)

```python
from processing.functions.resolve_company import resolve_company

resolve_company("삼전")
# {"status": "exact", "matched": True, "ticker": "005930", "company": "삼성전자", "sector": "IT",
#  "sector_l2": "반도체와반도체장비", "market": "KOSPI", "market_cap": 1.1e15, "tier": "T1",
#  "data_status": {...get_available_data_status 결과...}, "candidates": [], "match_status": "alias", ...}

resolve_company("삼성")
# {"status": "ambiguous", "matched": False, "candidates": [삼성전자, 삼성바이오로직스, ... 최대 5개], ...}
```

- `status`: `exact` / `ambiguous` / `not_found`
- 이행 기간: 기존 호출부(오케스트레이터·트렌드 리포트)가 쓰는 `matched`(exact일 때만 true), `ticker`, `company`, `sector`를 그대로 주고, `match_status`·`match_confidence`도 남깁니다
- 조회 실패 시 예외 대신 `not_found`와 `"error": "company_lookup_unavailable"`

## search_companies(query, limit=10)

후보 목록(채팅 5개, 자동완성 10개). 각 후보는 `ticker`, `company`, `sector`(WICS 대분류), `market_cap`에 `match`, `sector_l2`, `market`, `tier`, `is_preferred`를 더한 것입니다.

## extract_company_mentions(text)

```python
from processing.functions.extract_company_mentions import extract_company_mentions

extract_company_mentions("삼전이랑 하이닉스 비교해줘")
# [{"mention": "삼전", "position": 0, "status": "exact", "ticker": "005930", ...},
#  {"mention": "하이닉스", "position": 5, "status": "exact", "ticker": "000660", ...}]
```

- 사전에 있는 표현만 뽑습니다(정식명, 6자리 종목코드, 별칭, 그룹 별칭). 사전에 없는 표현은 오케스트레이터가 되묻습니다
- 긴 표현을 먼저 보고 겹치지 않게 뽑습니다(`카카오뱅크`를 `카카오`로 뽑지 않음). 뒤에 조사가 붙어도 인정합니다(`삼전이랑`, `하이닉스의`)
- 앞뒤로 다른 글자가 붙으면 뽑지 않습니다(`카카오톡`의 카카오, `SK하이닉스`의 SK)
- 흔한 낱말과 같은 정식명(대상, 동양, 선진, 진도 등, `extract_exclude`)은 문장에서는 뽑지 않습니다. `resolve_company("대상")`처럼 직접 물으면 정상 처리됩니다
- 같은 종목은 처음 한 번만, 문장에 나온 순서대로. 그룹 별칭은 `ambiguous`와 사전에 적은 그룹 종목을 후보로 줍니다

## find_terms(text)

```python
from processing.functions.find_terms import find_terms

find_terms("반도체 업종 PER이랑 외국인 순매수")
# {"sectors": [{"term": "반도체", "sector_level": "l2", "sector": "반도체와반도체장비"}],
#  "metrics": [{"term": "PER", "metric_id": "per"}, {"term": "외국인순매수", "metric_id": "foreign_net_buy_20d"}]}
```

- 업종: WICS 대분류·중분류 이름(DB)과 줄임말(`sector_terms`). 지표: `get_metric`의 `metric_id`로 바꿉니다(`metric_terms`)
- 한글 용어는 공백을 무시하고, 영문 용어는 다른 영단어의 일부가 아닐 때만 인정합니다(`PERFORMANCE`의 PER은 아님)

## 사전 고치기

`processing/config/company_terms.json`에 추가하면 됩니다. `processing/tests/test_company_lookup.py`가 종목코드 형식과 지표 이름(`get_metric`에 있는지)을 확인합니다.
