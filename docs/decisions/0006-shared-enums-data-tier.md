# 0006. `AgendaId`·`DataTier`·`Tier` 공용 열거형은 data-pipeline에 두고, API 계약서와 같은 값을 쓴다

- 상태: 채택
- 결정일: 2026-11
- 결정자: 수경
- 의견을 준 사람: 유민
- 출처: 카톡 대화(유민→수경 질문 1차 7번), PR #30

## 배경

토론 안건(`AgendaId`), 종목 데이터 등급(`DataTier`), 종목 등급(`Tier`) 값을 backend와 data-pipeline이 각자 문자열로 쓰고 있었습니다. 같은 값을 다르게 쓰면 조용히 매칭에 실패합니다.

## 결정

- 세 열거형을 **data-pipeline의 공용 모듈**에 두고, 값은 API 계약서(`docs/api/openapi.yaml`)와 같게 합니다.
- **`DataTier`** 값은 `report`, `news_only`, `disclosure_only`, `derived_only`, `macro_only`입니다. `get_agent_context` 결과에 들어갑니다.
- **`Tier`**(종목 등급) 값은 `T0`, `T1`, `T2`입니다. `resolve_company`가 `tier`와 `data_status`를 함께 돌려줍니다.

## 영향

- 새 값을 추가할 때는 열거형과 API 계약서를 같은 PR에서 함께 고칩니다.
- backend도 문자열을 직접 쓰지 않고 이 열거형을 가져다 씁니다.

## 참고

- PR #30 (공용 열거형), `docs/api/openapi.yaml`의 `AgendaId`, `Tier`
