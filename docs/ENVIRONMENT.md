# 환경변수와 GitHub Actions 비밀값 관리

어떤 값을 어디에 두는지, GitHub `Settings > Secrets and variables > Actions`에 무엇을 넣는지 정리한 문서입니다.
코드에서 설정을 읽는 규칙은 [CODE_CONVENTIONS.md](CODE_CONVENTIONS.md#설정과-환경변수)를 봅니다.

> 이 저장소는 **공개(Public)** 저장소입니다. 코드, 커밋 기록, GitHub Actions 로그를 누구나 볼 수 있습니다.

## 목차

- [원칙](#원칙)
- [값을 두는 위치](#값을-두는-위치)
- [GitHub에 등록할 값](#github에-등록할-값)
- [Environment 구성](#environment-구성)
- [워크플로에서 쓰는 방법](#워크플로에서-쓰는-방법)
- [저장소 보안 설정](#저장소-보안-설정)
- [키 교체와 유출 대응](#키-교체와-유출-대응)
- [참고 자료](#참고-자료)

---

## 원칙

1. **설정은 코드와 분리합니다.** 배포마다 달라지는 값(접속 주소, 인증키, 배포별 설정)은 환경변수로 받습니다. 기준은 "지금 이 코드를 공개해도 비밀이 새지 않는가"입니다 (Twelve-Factor App).
2. **비밀값은 Secret, 일반 설정은 Variable에 둡니다.**
   - Secret은 로그에서 자동으로 가려지지만, 값을 변형하면 가려지지 않을 수 있습니다.
   - Variable은 로그에 그대로 보입니다.
3. **값 하나에 Secret 하나를 씁니다.** 로그 가림은 정확히 일치하는 문자열만 찾기 때문에, JSON 묶음에 넣으면 일부가 그대로 보일 수 있습니다 (GitHub 보안 가이드).
4. **필요한 곳에만 줍니다.**
   - 운영 데이터용 비밀값은 저장소 전체가 아니라 Environment에 넣고, `main` 브랜치에서 도는 작업만 읽게 합니다.
   - 워크플로의 `GITHUB_TOKEN`도 기본 읽기 전용으로 둡니다 (OWASP 최소 권한).
5. **운영과 개발 자격증명을 나눕니다.** 최소한 운영 DB와 개인 개발 DB의 접속 정보는 달라야 합니다 (OWASP).
6. **필수 값은 시작할 때 확인합니다.** 빠진 필수 값은 작업 첫 단계에서 이름을 적어 실패시킵니다. 처리 도중에 실패하게 두지 않습니다.

## 값을 두는 위치

| 위치 | 무엇을 | 누가 봄 |
| --- | --- | --- |
| 로컬 `.env` (커밋 안 함) | 개인 개발용 키와 설정 | 본인 |
| `.env.example` (커밋함) | 변수 이름, 설명, 비밀이 아닌 기본값 | 공개 |
| GitHub Secret (Environment) | 자동화 작업이 쓰는 비밀값 | 워크플로 실행 중에만 |
| GitHub Variable | 자동화 작업이 쓰는 비밀이 아닌 설정 | 저장소 협업자 |
| Vercel 환경변수 | 프런트엔드 빌드 설정 | Vercel 프로젝트 멤버 |
| 코드 상수 | 바뀌지 않는 규칙과 외부 API 고정값 | 공개 |

- **Vercel에 둘 것:** 프런트엔드 값(`VITE_*`)은 Vercel 프로젝트 설정에 둡니다. Vercel Git 연동으로 배포하면 GitHub에 Vercel 토큰을 둘 필요가 없습니다. `VITE_*` 값은 빌드 결과물에 공개되므로 비밀값을 넣지 않습니다.
- **어디에도 두지 않을 것:** 일회성 운영 스위치(`ALLOW_MASS_DELIST` 등)는 상시 Variable로 두지 않습니다. 수동 실행(`workflow_dispatch`) 입력값으로 받아서, 필요할 때만 켜고 기록이 남게 합니다.

## GitHub에 등록할 값

지금은 `.github/workflows`가 없습니다. 아래는 데이터 적재를 정기 실행할 때 필요한 값을 미리 정리한 것입니다.
- **CI(테스트·빌드)에는 비밀값이 필요 없게 유지합니다.** 테스트는 외부 API를 목으로 대체합니다.
- **담당자 칸은 팀이 채웁니다.** 키를 발급받은 사람이 담당자이고, 교체와 폐기를 책임집니다.

### Secrets (Environment `production`)

| 이름 | 쓰는 곳 | 필수 | 담당자 | 비고 |
| --- | --- | --- | --- | --- |
| `SUPABASE_DB_URL` | 모든 Supabase 적재기 | 필수 | | 운영 DB 접속 주소(Session pooler). 개발용과 분리 |
| `DART_API_KEY` | 재무·공시 수집, 종목 마스터 | 필수 | | 하루 요청 한도 약 2만 건 |
| `ECOS_API_KEY` | `macro_loader` | 필수 | | |
| `KRX_ID` | `market_loader` (pykrx 로그인) | 필수 | | **개인 계정 대신 팀 전용 계정**을 만들어 씁니다 |
| `KRX_PW` | `market_loader` | 필수 | | 위와 같음 |
| `KIS_APP_KEY` | 목표주가 수집 | 기능 사용 시 | | |
| `KIS_APP_SECRET` | 목표주가 수집 | 기능 사용 시 | | |
| `NAVER_CLIENT_ID` | 뉴스 수집 | 기능 사용 시 | | |
| `NAVER_CLIENT_SECRET` | 뉴스 수집 | 기능 사용 시 | | |
| `UPSTAGE_API_KEY` | 임베딩, 에이전트 LLM | 필수 | | |
| `PINECONE_API_KEY` | 벡터 적재·검색 | 필수 | | |

나중에 GitHub Actions에서 Supabase 마이그레이션을 배포한다면 `SUPABASE_ACCESS_TOKEN`과 `SUPABASE_DB_PASSWORD`를 추가합니다. 프로젝트 ID는 Variable에 둡니다.

### Variables

| 이름 | 예시 값 | 범위 | 비고 |
| --- | --- | --- | --- |
| `PINECONE_INDEX` | `ant-reports` | production | 인덱스 이름은 비밀이 아님 |
| `SCHEDULE_TIMEZONE` | `Asia/Seoul` | 저장소 | |
| `MACRO_DATA_PROVIDER` | `ecos` | 저장소 | |
| `PRICE_DATA_PROVIDER` | `naver` | 저장소 | |
| `REQUEST_INTERVAL_SECONDS` | `1.5` | 저장소 | 외부 사이트 요청 간격 |
| `MAX_REPORTS_PER_COMPANY` | `10` | 저장소 | 수집 상한 |
| `MAX_TOTAL_REPORTS` | `50` | 저장소 | 수집 상한 |
| `DEBATE_LLM_MODEL` 등 `*_LLM_MODEL` | `solar-mini` | 저장소 | 코드 기본값과 다를 때만 등록 |

코드에 기본값이 있고 바꿀 일이 없는 설정은 등록하지 않습니다. 등록한 Variable이 늘어날수록 "실제 값이 어디서 왔는지" 추적하기 어려워집니다.

## Environment 구성

`Settings > Environments`에서 만듭니다.

| Environment | 용도 | 보호 규칙 |
| --- | --- | --- |
| `production` | 정기 적재, 운영 DB에 쓰는 작업 | **배포 브랜치를 `main`으로 제한**. 정기 실행(cron)은 사람이 승인할 수 없으므로 필수 승인자는 두지 않음 |
| `production-manual` (필요할 때) | 전체 백필, 대량 상장폐지 허용 같은 수동 작업 | **필수 승인자 1명**. 승인 전에는 비밀값을 읽을 수 없음 |

- **Environment에 둡니다:** 다른 브랜치나 PR에서 도는 워크플로가 운영 비밀값을 읽지 못하게 하려면, 비밀값을 저장소 Secret이 아니라 Environment Secret에 둡니다.
- **우선순위:** 같은 이름이 여러 단계에 있으면 Environment > 저장소 > 조직 순으로 적용됩니다.

## 워크플로에서 쓰는 방법

```yaml
# .github/workflows/data-daily.yml (예시)
name: 데이터 일일 적재
on:
  schedule:
    - cron: "30 9 * * 1-5"   # UTC 09:30 = KST 18:30, 장 마감 후
  workflow_dispatch:

permissions:
  contents: read             # GITHUB_TOKEN 최소 권한

jobs:
  market:
    runs-on: ubuntu-latest
    environment: production  # 이 Environment의 Secret만 읽음
    env:
      TZ: Asia/Seoul
      SUPABASE_DB_URL: ${{ secrets.SUPABASE_DB_URL }}
      KRX_ID: ${{ secrets.KRX_ID }}
      KRX_PW: ${{ secrets.KRX_PW }}
      DART_API_KEY: ${{ secrets.DART_API_KEY }}
      REQUEST_INTERVAL_SECONDS: ${{ vars.REQUEST_INTERVAL_SECONDS }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r data-pipeline/requirements.txt
      - run: python -m crawling.market_loader
        working-directory: data-pipeline
```

- **필요한 값만 넘깁니다.** 비밀값은 그 값이 필요한 job에만, 이름을 하나씩 적어 넘깁니다. `${{ toJSON(secrets) }}`처럼 전부 넘기지 않습니다.
- **비밀값을 출력하지 않습니다.** `echo`, `set -x`, 디버그 출력으로 비밀값을 찍지 않습니다. 비밀값에서 만든 값(토큰, 인코딩한 값)은 `::add-mask::`로 가립니다.
- **`pull_request_target`은 쓰지 않습니다.** 이 트리거는 외부 PR 코드를 비밀값과 함께 실행할 수 있어 위험합니다. 외부 포크에서 온 PR의 `pull_request` 워크플로에는 비밀값이 전달되지 않으므로, CI는 비밀값 없이 통과하게 만듭니다.
- **cron은 UTC 기준입니다.** 코드의 기준일은 [CODE_CONVENTIONS.md](CODE_CONVENTIONS.md#날짜와-시각)대로 KST로 계산합니다.

## 저장소 보안 설정

관리자가 한 번 켜 두면 되는 설정입니다.

| 위치 | 설정 | 이유 |
| --- | --- | --- |
| `Settings > Advanced Security` | **Secret scanning**, **Push protection** 켜기 | 키가 커밋되면 push 단계에서 막음. 공개 저장소는 무료 |
| `Settings > Actions > General > Workflow permissions` | **Read repository contents** 선택 | `GITHUB_TOKEN` 기본 권한을 읽기 전용으로 |
| `Settings > Actions > General > Fork pull request workflows` | 외부 기여자 워크플로 실행 시 **승인 필요** | 공개 저장소에서 남의 코드가 러너에서 돌지 않게 |
| `Settings > Environments > production` | 배포 브랜치 `main`으로 제한 | 다른 브랜치에서 운영 비밀값 사용 차단 |

## 키 교체와 유출 대응

- **정기 교체:** 비밀값은 정기적으로 교체합니다. 기준은 90일마다, 그리고 팀원이 빠질 때입니다. 위 표의 담당자가 교체합니다.
- **유출되면 순서대로:**
  1. **즉시 폐기:** 발급처(DART, Supabase 등)에서 키를 먼저 폐기합니다.
  2. **새 키 등록:** 새 키를 발급해 GitHub Secret과 각자의 `.env`를 갱신합니다.
  3. **기록 확인:** 커밋 기록에 남았다면 키는 이미 공개된 것으로 봅니다. 기록을 지우는 것보다 폐기가 먼저입니다.
- **안 쓰는 값은 지웁니다.** 사용하지 않게 된 Secret은 바로 삭제합니다.

## 참고 자료

- [GitHub Docs: Secrets](https://docs.github.com/en/actions/concepts/security/secrets)
- [GitHub Docs: Secrets reference (이름 규칙·우선순위·한도)](https://docs.github.com/en/actions/reference/security/secrets)
- [GitHub Docs: Variables reference](https://docs.github.com/en/actions/reference/workflows-and-actions/variables)
- [GitHub Docs: Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [The Twelve-Factor App: Config](https://12factor.net/config)
