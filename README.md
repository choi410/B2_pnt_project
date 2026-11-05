# B2 프로젝트 업무 관리 v1

회의록에서 고객 요구·설계변경·후속 조치를 정리하고, 담당자의 조치와 PM의 검토, 회의별 요구사항 변경 이력을 관리하는 웹서비스입니다.

버전은 **1.0.0**, Git 브랜치와 릴리스 태그는 **v1**입니다. FastAPI·SQLite 서버와 React·TypeScript 화면으로 구성됩니다.

## 포함된 기능

- Word 회의록과 텍스트 입력, 로컬 AI 분석 또는 직접 검토
- 프로젝트·안건별 업무 흐름과 결정 사항 관리
- 담당자·기한·진행 상태 수정, 조치 기록, PM 완료 검토와 변경 이력
- 회의별 요구사항의 요청값·승인값, 원문 근거와 원본 Word 확인
- 이전 회의의 정보만 참조하는 요구사항 AI 비교와 사용자 검토
- 웹 전용·GPU Docker 실행, 임시 HTTPS 주소를 통한 외부 공유
- 일시적인 연결 중단 후 요구사항 화면 복구와 작성 중인 검토 메모 유지

AI는 Qwen3-4B-Instruct-2507의 4비트 배포 모델을 사용합니다. 생성형 AI가 후보를 추출하고 Pydantic과 업무 규칙이 형식·원문 근거 등을 검증합니다. 검증 엔진은 별도의 생성형 AI 모델이 아닙니다. 결과의 정확성과 반영 여부는 사용자가 원문과 대조해 확인합니다.

## 저장소에 포함하지 않는 항목

AI 모델 가중치·토크나이저·모델 설정, 설치 환경, `node_modules`, 실행 로그, 현재 사용 중인 SQLite DB와 외부 공유 주소는 제외합니다. GitHub에서 받은 새 복사본은 빈 DB로 시작하며, 기존 PC의 회의록이나 업무 기록이 자동으로 나타나지 않습니다.

화면 빌드 결과인 `b2-service/dist`는 포함되어 있어, 아래 Windows 실행에는 Node.js가 필요하지 않습니다.

## Windows에서 실행

Python 3.12 64비트가 필요합니다. 저장소 전체를 내려받은 뒤 실행합니다.

```powershell
git clone --branch v1 https://github.com/choi410/B2_pnt_project.git
cd B2_pnt_project
.\01_setup.cmd
.\05_start_manual.cmd
```

접속: [http://127.0.0.1:8766/](http://127.0.0.1:8766/)

모델 없이도 프로젝트 생성, 회의록 직접 검토와 업무 관리를 사용할 수 있습니다. 설치한 모델을 자동으로 내려받지는 않습니다.

## Docker에서 실행

Docker Desktop의 Linux 엔진과 Python 3.12를 준비합니다. 최초 실행은 기존 로컬 DB가 없으면 생성된 빈 로컬 DB를 준비한 뒤 도커용 복사본을 만듭니다.

```powershell
.\01_setup.cmd
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'b2-service'); import server; server.initialize()"
.\08_start_docker_manual.cmd
```

접속: [http://127.0.0.1:8767/](http://127.0.0.1:8767/)

기존 로컬 기록이 있으면 첫 Docker 실행 때 SQLite 백업 기능으로 복사합니다. 이후 도커의 `docker-data`와 로컬의 `b2-service/data`는 별도로 저장되며 자동으로 동기화되지 않습니다. 종료는 `07_stop_docker.cmd`입니다.

## AI 모델을 사용하는 경우

1. `b2-model/model_source.json`에 기록된 모델과 리비전을 확인합니다.
2. 해당 모델의 가중치·토크나이저·설정 파일 전체를 `b2-model/models/base/`에 준비합니다.
3. Windows 직접 실행은 `03_setup_ai.cmd`로 구성요소를 설치한 뒤 `04_check.cmd`, `02_start.cmd` 순서로 실행합니다.
4. Docker GPU 실행은 `06_start_docker.cmd`를 사용합니다. Windows에서는 WSL 2 기반 Docker Desktop과 NVIDIA GPU 지원이 필요합니다.

최초 분석 시 모델을 로드합니다. 웹 서버가 실행됐다는 것만으로 모델 로드나 생성 품질이 검증된 것은 아닙니다.

## 가상자료로 확인하기

‘요구사항 이력’ 화면에서 **개발용 가상자료 불러오기**를 누르면 PNT-SIM-001의 회의 5건·요구사항 12개·기준 이력 32건을 등록할 수 있습니다. 이 기준 이력은 제공된 가상자료이며 AI가 생성한 결과가 아닙니다.

추가 가상 회의록은 [b2-service/sample](b2-service/sample)에 있습니다. PNT 스타일의 속도·납기·안전커버 협의 회의록도 포함했습니다.

## 다른 장소에서 접속하기

모델이 준비된 GPU 구성에서는 `09_start_internet_share.cmd`를 실행하고, 표시된 임시 HTTPS 주소를 전달합니다. `10_stop_internet_share.cmd`는 외부 공유만 종료하며 로컬 사이트와 DB는 유지합니다.

사용자가 선택한 체험 구성은 이메일 등록·로그인 없이 링크로 접속하는 방식입니다. **주소를 아는 사람은 조회·수정할 수 있습니다.** 체험 역할은 실제 사용자 인증이 아닙니다. PC와 Docker가 켜져 있어야 하며, 공유 연결을 새로 만들면 주소가 달라집니다. 실제 업무 자료를 상시 운영하는 서비스에는 별도의 인증·권한 설계가 필요합니다.

자세한 방법은 [DOCKER_README.md](DOCKER_README.md)를 확인하세요.

## 개발과 검증

```powershell
cd b2-service
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd b2-service
..\.venv\Scripts\python.exe -m pytest -q
cd ..
.\.venv\Scripts\python.exe manage.py verify
```

`manage.py verify`는 배포 파일의 SHA-256을 확인합니다. DB와 모델은 검사에서 제외됩니다. 소스나 빌드 결과를 의도적으로 수정하면 해당 파일의 무결성 목록도 갱신해야 합니다.

## v1에서 확인된 제한

- 기한에 `GA Rev.B` 같은 개정 단계가 들어가면 날짜 필드 검증에 실패해 회의록 전체 분석이 실패할 수 있습니다. 원인과 처리 방향만 확인했으며 v1에는 수정이 적용되지 않았습니다.
- 현재 AI 입력은 4,096토큰, 문서 입력은 12,000자·Word 파일 4MB로 제한됩니다. 긴 문서는 안건별로 나누어야 합니다.
- 이력 비교용 가져오기는 제공된 PNT-SIM-001 자료를 대상으로 합니다. 다른 프로젝트의 연속 회의가 자동으로 같은 요구사항 이력 구조로 등록되는 기능은 제공하지 않습니다.
- 사용자별 로그인, 클라우드 DB 자동 동기화, 상시 운영용 고정 주소는 포함하지 않습니다.

## 문서와 라이선스

- [v1 릴리스 설명](docs/releases/v1.md)
- [회의록 분석 오류 보고서 양식과 작성 예시](docs/회의록_분석오류_보고서_양식_및_작성예시.md)
- [도커 실행과 외부 공유](DOCKER_README.md)
- [이전 배포본 인수인계 기록](HANDOFF_NEXT_PC.md): 2026-11-04의 참고 자료이며 현재 환경은 위 설명을 우선합니다.
- [외부 구성요소와 모델 출처](THIRD_PARTY.txt), [라이선스 문서](licenses)

팀 애플리케이션과 문서에 새로운 오픈소스 라이선스를 임의로 부여하지 않았습니다.
