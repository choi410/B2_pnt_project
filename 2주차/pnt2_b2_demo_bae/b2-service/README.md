# b2-service

PNT 회의록 서비스 v4의 웹 서버와 화면입니다. FastAPI 서버 하나가 API와 화면을 함께 제공합니다.
설치·실행 방법과 AI 모델 준비는 상위 폴더의 [README.md](../README.md)를 먼저 봅니다.

## 실행

상위 폴더의 `02_서비스실행.cmd`를 사용합니다. 직접 실행하려면 이 폴더에서 다음을 실행합니다.

```powershell
..\b2-model\.venv\Scripts\python.exe -m uvicorn work.v3.server:app --host 127.0.0.1 --port 8773
```

- 실행 진입점은 `work.v3.server:app` 입니다. 이 폴더의 `server.py`는 직접 실행하지 않습니다.
- 접속 주소는 http://127.0.0.1:8773/ 입니다. 포트와 허용 주소는 `work/v17/team_config.py`에 있습니다.

## 폴더 구성

| 경로 | 내용 |
| --- | --- |
| `work/v3/` | 현재 화면과 API. 회의록 등록·분석, 본문 검색(`search_engine.py`, `search.html`), 휴지통, 로그인 화면(`login.html`), 관리 화면(`admin.html`) |
| `work/v17/` | v3가 함께 쓰는 공통 코드. 저장소, 로그인·권한, 문서 처리, 변경이력, AI 질문. 삭제하면 안 됩니다 |
| `supabase/schema.sql` | Supabase에 만드는 표와 트리거. 서버 첫 실행 때 자동 적용됩니다 |
| `.env.example` | Supabase 연결 설정 예시. `.env`로 복사해 값을 채웁니다 |
| `data/v4/` | 로컬 데이터(SQLite, 업로드 원본). Git에 올리지 않습니다 |
| `server.py`, `workflow.py` | 이전 단일 사용자 버전. `work/v3`가 일부 함수를 가져다 씁니다 |
| `workspace_ai.py` | 로컬 AI 모델 호출 공통 코드 |
| `convert_preview.ps1` | Word 원본을 PDF 미리보기로 바꿀 때 쓰는 스크립트 |
| `requirements*.txt` | Python 의존성. `-lock`은 버전 고정, `-dev`는 테스트용 |
| `package.json` | 화면 빌드와 화면 로직 테스트 명령 |

### 로그인·권한 관련 파일

| 파일 | 역할 |
| --- | --- |
| `work/v17/storage.py` | `.env` 유무에 따라 Supabase Postgres 또는 로컬 SQLite를 선택 |
| `work/v17/supabase_auth.py` | Supabase Auth 호출 (비밀번호 확인, 계정 생성, 비밀번호 변경) |
| `work/v17/accounts.py` | 로그인 처리와 사용자·역할별 기능·프로젝트 참여자 관리 API |
| `work/v17/server.py` | 세션 확인(`user`), 역할별 기능 확인(`permissions`, `require`), 프로젝트 접근 확인(`project`) |

## 저장 방식

| 상태 | 로그인 | 데이터 |
| --- | --- | --- |
| `.env` 없음 | 이름 선택(테스트용) | 이 PC의 `data/v4/workspace.sqlite3` |
| `.env` 설정 | 이메일·비밀번호 (Supabase Auth) | Supabase Postgres |

`.env`에는 `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_DB_URL` 세 값이 모두 있어야 합니다.
하나라도 빠지면 서버가 시작하지 않고 어떤 값이 필요한지 알려 줍니다.
`.env`는 비밀 값이므로 Git에 올리거나 공유하지 않습니다.

## 주요 주소

| 주소 | 내용 |
| --- | --- |
| `/` | 업무 화면. Supabase 설정 시 로그인하지 않으면 `/login`으로 이동 |
| `/login` | 이메일 로그인 화면 |
| `/search` | 회의록 본문 검색, 원문 보기, 근거 자료 내보내기 |
| `/admin` | 사용자, 역할별 기능, 프로젝트 참여자 관리 |
| `/api/health` | 서버 상태와 현재 저장 방식 확인 |
| `/api/me` | 로그인한 사용자와 허용된 기능 |
| `/docs` | API 목록 (FastAPI 자동 문서) |

## 테스트

```powershell
..\b2-model\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
..\b2-model\.venv\Scripts\python.exe -m pytest work/v3 -q
```

- `work/v3` 테스트는 `.env`가 있어도 임시 로컬 데이터만 사용합니다.
- Supabase 로그인·권한 테스트(`work/v17/test_supabase_accounts.py`)는 비어 있는 테스트용 Postgres가 필요하며 따로 실행합니다. 방법은 상위 README의 "개발" 절에 있습니다.

## 화면 수정

화면 소스는 `work/v3/*.jsx`이고, 빌드 결과인 `work/v3/workspace.html`을 서버가 그대로 제공합니다.
소스를 고친 뒤에는 Node.js로 다시 빌드해야 반영됩니다.

```powershell
npm ci
npm run build
npm test
```

`login.html`, `admin.html`, `search.html`은 빌드 없이 파일을 고치면 바로 반영됩니다.
