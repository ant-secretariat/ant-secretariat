# ant-secretariat-backend

## 온보딩 (`onboarding/`, `functions/`, `api/onboarding.py`)

7개 질문 응답을 받아 `users` 테이블의 5개 필드(`risk_profile`, `investment_goal`,
`investment_amount_range`, `investment_experience`, `interest_sectors`)로 변환해
저장하고, 다른 에이전트가 유저 컨텍스트를 조회할 수 있게 한다.

- `onboarding/processor.py` — DB 접근 없는 순수 변환 로직 (점수 산출, 섹터 검증)
- `functions/save_onboarding.py` — 변환 후 `users` 테이블에 UPSERT
- `functions/get_user_context.py` — `users` 테이블 조회, JSON 필드 파싱
- `api/onboarding.py` — `POST /onboarding`, `GET /users/{user_id}/context` (APIRouter;
  메인 앱에 `include_router`로 등록되는 것을 전제로 함)

### 중요: `ant-secretariat-data-pipeline`에 대한 의존성

`users` 테이블을 포함한 DB 스키마(`CREATE TABLE`)는 이 레포가 아니라
`ant-secretariat-data-pipeline` 레포의 `crawling/db/schema.sql`이 canonical로 소유한다.
`reports.db` 하나를 crawling/processing/backend가 함께 쓴다.

이 레포는 자체 DB 접근 계층을 새로 만들지 않고, `db.py`를 통해
`ant-secretariat-data-pipeline`의 `crawling.db.database.Database`를 그대로 재사용한다.
연결은 `sys.path` 조작이 아니라 `requirements.txt`의 editable install로 이루어진다:

```
-e ../ant-secretariat-data-pipeline
```

**두 레포가 같은 부모 디렉토리 아래 형제(sibling)로 클론되어 있어야 한다**
(로컬/동일 서버 배포 기준):

```
투빅스/
├── ant-secretariat-backend/       (이 레포)
└── ant-secretariat-data-pipeline/  (pyproject.toml로 pip 설치 가능한 패키지)
```

배포 구조가 바뀌어 두 레포가 다른 위치에 있게 되면 `requirements.txt`의 이 경로를
재검토해야 한다 (예: git URL 설치로 전환).

## 설치 및 테스트

```bash
pip install -r requirements.txt   # -e ../ant-secretariat-data-pipeline 포함
cp .env.example .env
pytest
```
