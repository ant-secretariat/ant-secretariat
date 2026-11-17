# AI 에이전트 작업 규칙

이 저장소에서 코드를 쓰는 모든 AI 에이전트(Claude Code, Codex, Cursor 등)는 작업 전에 아래 문서를 읽고 따릅니다.

- [docs/CODE_CONVENTIONS.md](docs/CODE_CONVENTIONS.md) — 날짜·종목코드·단위·빈 값·이름·설정·로그 형식
- [docs/CONVENTIONS.md](docs/CONVENTIONS.md) — 브랜치, 커밋, PR, 리뷰 규칙
- [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md) — 환경변수와 비밀값을 두는 위치
- [docs/decisions/](docs/decisions/README.md) — 팀 의사결정 기록(ADR). 종목 범위, 지표 ID, 저장소 같은 합의된 결정. 코드가 결정과 다르면 결정을 먼저 확인합니다.

## 반드시 지킬 것

1. 오늘 날짜는 KST로 구합니다. `date.today()`와 타임존 없는 `datetime.now()`를 쓰지 않습니다.
2. 날짜는 `YYYY-MM-DD`, 시각은 타임존이 붙은 ISO 8601로 저장하고 주고받습니다.
3. 종목코드는 6자리 문자열입니다. `int`로 바꾸지 않습니다.
4. 금액은 원 단위 정수입니다. 퍼센트 필드는 이름 끝에 `_pct`를 붙이고, 확률은 `0~1` 소수로 씁니다.
5. 모르는 값은 `null`로 둡니다. 0이나 빈 문자열로 채우지 않습니다. 외부 응답이 비면 "전부 삭제"로 해석하지 않습니다.
6. 비밀값을 코드, 로그, 커밋, `VITE_*` 변수에 넣지 않습니다. 새 환경변수는 `.env.example`에 설명과 함께 추가합니다.
7. 필수 환경변수는 프로그램 시작 시점에 확인하고, 빠지면 이름을 적어 종료합니다.
8. 여러 건을 처리하는 배치는 한 건의 실패를 격리하고, 실패 비율이 높으면 0이 아닌 종료 코드로 끝냅니다.

## 영역별 확인 명령

| 영역 | 명령 |
| --- | --- |
| frontend | `cd frontend && npm run build` |
| data-pipeline | `cd data-pipeline && python -m pytest crawling/tests -q` |
| backend | `cd backend && python -m pytest -q` |
