# OndoTrip (그날의 온도) — 공공데이터 기반 구글 블로그 자동 포스팅

한국관광공사 국문 관광정보 서비스(`KorService2`, 매뉴얼 Ver 4.4) Open API에서 국내 여행지·음식점·숙박·여행코스 정보를 수집하고, Gemini AI 및 무료 지도(OpenStreetMap + 네이버/카카오/구글 지도 링크)를 결합해 Google Blogger(`https://ondotrip.blogspot.com/`)에 자동으로 글을 작성하는 Python 도구입니다.

## 프로젝트 구조

- `config.py`: `.env` 환경변수 로드, 관광타입(`contentTypeId`) 및 법정동 시도코드(`lDongRegnCd`) 매핑
- `tour_api.py`: `KorService2` API 클라이언트 (`areaBasedList2`, `searchKeyword2`, `detailCommon2`, `detailIntro2`, `detailInfo2`, `detailImage2`, `detailPetTour2`)
- `writer.py`: Gemini 원고 생성(폴백 포함) 및 반응형 HTML 생성, 무료 지도 임베드, 공공누리(Type1/Type3) 출처 표기
- `blogger_client.py`: Google Blogger API v3 OAuth 2.0 인증(`token.json`) 및 글 임시저장/발행
- `history_store.py`: `posted_history.json` 기반 중복 포스팅 방지
- `main.py`: CLI 실행 진입점
- `run_post.bat`: Windows 실행 배치 파일

## 최초 1회 설정 및 인증

가상환경(`.venv`)과 패키지는 이미 설치되어 있습니다. Blogger에 글을 올리기 전, 최초 1회 Google OAuth 로그인으로 `token.json`을 발급받으세요.

```powershell
.\.venv\Scripts\python.exe main.py --auth-only
```

브라우저 창이 열리면 블로그 소유자 구글 계정으로 로그인하고 권한을 허용하면 `token.json`이 생성됩니다.

## 블로그 카테고리 구조 (4대 공식 카테고리 + 지역 서브)

모든 게시물은 Blogger 태그(Label)가 곧 카테고리 및 하위 지역 메뉴 역할을 하도록 아래 2개 라벨이 자동 부여됩니다.

- **상위 카테고리**: `그날의 장소`, `그날의 미식`, `그날의 쉼터`, `그날의 여정`
- **하위 지역 라벨**: `<상위 카테고리>-<지역>` (예: `그날의 장소-강원`, `그날의 미식-제주`, `그날의 쉼터-경기`, `그날의 여정-강원`)
- 사이드바 계층형 카테고리 위젯 코드는 [`category_widget.html`](category_widget.html)에 준비되어 있습니다.

- **`그날의 장소`** (`--category 장소`): 관광지, 문화시설, 레포츠, 쇼핑 *(일회성 행사/축제는 자동 제외)*
- **`그날의 미식`** (`--category 미식`): 카페, 맛집, 음식점 (`contentTypeId=39`)
- **`그날의 쉼터`** (`--category 쉼터`): 숙박, 캠핑장, 글램핑, 펜션, 한옥스테이 (`contentTypeId=32` 및 캠핑·야영장)
- **`그날의 여정`** (`--category 여정`): 여행 코스 (`contentTypeId=25`)

## 사용 예시

### 1. 자동 배분 모드 (권장 선정 기준 전체 적용)
`--mode auto`는 아래 운영 기준으로 대상을 자동 선별합니다.
- **축제·행사 제외**: 일회성 행사(`15`) 자동 차단
- **여정 10:1 규칙**: `그날의 장소` + `그날의 미식` + `그날의 쉼터` 누적 10건마다 `그날의 여정` 1건 자동 편성
- **테마 키워드 & 지역 균형**: 인기 테마(`수목원`, `한옥`, `카페`, `캠핑장`, `글램핑` 등)와 17개 권역 순환
- **품질 필터**: 카테고리별 최소 개요 길이(장소 120자 / 미식·쉼터·여정 40자 이상) 및 이미지 보유 여부 확인

```powershell
# 현재 카테고리 누적 현황 및 여정까지 남은 개수 확인
.\.venv\Scripts\python.exe main.py --status

# 자동 배분으로 하루 3편 업로드 (임시저장, 10개마다 자동으로 여정 1편 작성)
.\.venv\Scripts\python.exe main.py --mode auto --count 3
```

### 2. 로컬 HTML 미리보기만 생성 (업로드 없음)
```powershell
.\.venv\Scripts\python.exe main.py --preview-only --category 쉼터 --area 강원 --count 1
```
생성된 HTML은 `output/` 폴더에 저장되며 브라우저로 바로 열어 레이아웃을 확인할 수 있습니다.

### 3. 카테고리별 임시저장(Draft) 수동 업로드
```powershell
# 그날의 장소 (관광지)
.\.venv\Scripts\python.exe main.py --category 장소 --area 제주 --count 1

# 그날의 미식 (카페·맛집)
.\.venv\Scripts\python.exe main.py --category 미식 --area 서울 --keyword 카페 --count 1

# 그날의 쉼터 (숙박·캠핑장)
.\.venv\Scripts\python.exe main.py --category 쉼터 --area 경기 --keyword 캠핑장 --count 1

# 그날의 여정 (여행 코스)
.\.venv\Scripts\python.exe main.py --category 여정 --area 강원 --count 1
```
`--publish`를 붙이지 않으면 안전하게 **임시저장** 상태로 올라갑니다.

### 4. 키워드로 검색해 즉시 공개 발행
```powershell
.\.venv\Scripts\python.exe main.py --category 장소 --keyword 한옥마을 --count 1 --publish
```

### 5. 특정 콘텐츠 ID 직접 지정
```powershell
.\.venv\Scripts\python.exe main.py --content-id 126128 --preview-only
```

### 6. 이미 작성한 이력 무시하고 재작성
```powershell
.\.venv\Scripts\python.exe main.py --area 부산 --type 음식점 --count 1 --force
```

## 클라우드 무인 자동 실행 (Cloudflare Workers Cron + GitHub Actions)

로컬 PC 전원을 켜두지 않아도 [`Slack_AutoBot`](https://github.com/kkubunge/Slack_AutoBot)의 Cloudflare Workers Cron(`0 1 * * *`, **매일 오전 10:00 KST**)이 GitHub Actions([`.github/workflows/daily_post.yml`](.github/workflows/daily_post.yml))를 자동 실행하여 **즉시 공개 발행(`publish: true`)** 하고, 새로 발행된 글의 카테고리·제목·공개 링크를 Slack DM으로 자동 보고합니다.

### 필수 GitHub Repository Secrets (`Settings → Secrets and variables → Actions`)

| Secret 이름 | 설명 |
| :--- | :--- |
| `TOUR_API_KEY` | 공공데이터포털 `KorService2` 인증키 |
| `BLOGGER_BLOG_ID` | Google Blogger 블로그 ID |
| `BLOGGER_URL` | 블로그 URL (예: `https://ondotrip.blogspot.com/`) |
| `GEMINI_API_KEY` | Gemini API 키 |
| `GOOGLE_TOKEN_JSON` | 로컬 인증 완료된 `token.json` 파일 내용 전체 (`refresh_token` 포함) |
| `SLACK_BOT_TOKEN` | 완료/실패 보고용 Slack Bot Token (`xoxb-...`) |
| `SLACK_REPORT_CHANNEL_ID` | GitHub Actions 수동 실행 시 기본 보고 채널/DM ID (선택, 예: `D0CL64CQGJY`) |

> [!IMPORTANT]
> Google Cloud Console의 **OAuth 동의 화면**이 "테스트" 상태이면 Refresh Token이 7일마다 만료됩니다. 장기간 무인 실행을 위해서는 동의 화면 게시 상태를 **프로덕션**으로 전환해 두는 것을 권장합니다.

---

## 보안 및 저작권 주의사항

- `.env`, `client_secret_*.json`, `token.json`은 `.gitignore`에 등록되어 있으므로 GitHub 등 공개 저장소에 올리지 마세요.
- 한국관광공사 이미지 중 공공누리 제3유형(`Type3`)은 **출처 표시 및 원본 변경 금지**가 적용되므로, 본 도구는 이미지를 가공하지 않고 원본 URL 그대로 삽입하며 하단에 출처와 저작권 유형을 자동 표기합니다.
