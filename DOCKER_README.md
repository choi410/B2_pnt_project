# B2 도커 실행

Docker Desktop의 Linux 엔진을 켠 뒤 이 폴더에서 실행합니다.

GitHub에서 처음 받은 폴더에는 DB와 Python 실행 환경이 없습니다. Python 3.12 64비트를 준비하고 다음 초기 설정을 먼저 수행합니다.

```powershell
.\01_setup.cmd
.\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0,'b2-service'); import server; server.initialize()"
```

기존 DB가 있으면 초기화 함수는 기록을 유지하면서 필요한 테이블을 준비합니다. GPU 실행에는 모델 파일도 별도로 준비해야 합니다. 이후 아래 실행 파일을 사용합니다.

- `06_start_docker.cmd`: NVIDIA GPU를 사용해 AI 분석까지 실행
- `07_stop_docker.cmd`: 도커 서비스 종료. 회의록 데이터는 유지
- `08_start_docker_manual.cmd`: GPU 없이 조회·직접 검토 기능 실행

접속 주소: http://127.0.0.1:8767/

기존 실행 방식은 http://127.0.0.1:8766/ 에서 그대로 사용할 수 있습니다.

## 다른 장소에서 접속하기

`127.0.0.1`은 접속하는 사람 자신의 PC를 가리키므로 다른 사람에게 전달하는 주소가 아닙니다.

- `09_start_internet_share.cmd`: 현재 GPU 도커 서비스를 임시 HTTPS 주소로 공유합니다. 완료 후 표시되는 `https://...trycloudflare.com` 주소를 전달합니다.
- `10_stop_internet_share.cmd`: 외부 공유만 종료합니다. 로컬 사이트와 저장 자료는 유지합니다.
- `07_stop_docker.cmd`: 외부 공유와 B2 도커 서비스를 함께 종료합니다.

사용자 요청에 따라 이메일 등록·로그인 없이 링크로 접속하는 가상자료 체험 구성입니다.
주소를 아는 사람은 조회와 수정이 모두 가능합니다. 실제 기밀자료를 넣는 운영 서비스에는 별도의 인증이 필요합니다.
외부 방문자가 같은 프로젝트나 업무를 수정하면 현재 도커 DB에 저장됩니다.
이 PC와 Docker Desktop이 켜져 있어야 하며, 공유를 종료하고 새로 만들면 주소가 달라집니다.
공유 중 `09_start_internet_share.cmd`를 다시 실행하면 기존 연결이 정상일 때 같은 주소를 표시합니다.
`06_start_docker.cmd`와 `08_start_docker_manual.cmd`는 기본 로컬 전용 설정으로 시작합니다. 이후 외부 공유가 필요하면 09번을 실행합니다.

공유 연결은 [Cloudflare Quick Tunnel](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)을 사용합니다.
공유 연결용 컨테이너만 별도로 추가하고, PC의 로컬 포트·방화벽을 외부에 개방하지 않습니다.
현재 주소와 연결 상태는 `docker-data/internet-share.json` 및 아래 명령으로 확인할 수 있습니다.

```powershell
.\.venv\Scripts\python.exe internet_share.py status
```

## 데이터와 모델

처음 도커를 실행할 때 기존 회의록 DB를 SQLite 백업 기능으로 일관되게 복사합니다.
도커 데이터는 `docker-data/meetings.sqlite3`에 보관하며, 다음 실행부터는 이 파일을 계속 사용합니다.
기존 DB와 도커 DB는 별개이므로 양쪽에서 수정한 내용은 자동으로 동기화되지 않습니다.
운영할 주소를 하나 정해 사용하는 것을 권장합니다.

모델은 기존 `b2-model/models/base`를 읽기 전용으로 연결합니다.
모델 가중치와 회의록 DB는 이미지에 포함하지 않으며, 실행 시 모델을 자동으로 다운로드하지 않습니다.
AI 모델은 첫 분석 때 GPU에 로드됩니다. 웹 서버가 정상이어도 첫 분석은 시간이 더 걸릴 수 있습니다.
기존 사이트와 도커 사이트에서 AI 분석을 동시에 하면 GPU 메모리가 부족해질 수 있습니다.

Windows의 GPU 실행에는 WSL 2 기반 Docker Desktop과 NVIDIA 드라이버가 필요합니다. [Docker 공식 GPU 안내](https://docs.docker.com/desktop/features/gpu/)
첫 이미지 빌드에서는 Python·Node·CUDA 실행 구성요소를 다운로드하므로 수 GB의 용량과 시간이 필요합니다.
호스트의 127.0.0.1에만 포트를 연결하므로 현재 구성은 이 PC에서 사용하는 용도입니다.

## 직접 명령 실행

```powershell
.\.venv\Scripts\python.exe docker_manage.py start
.\.venv\Scripts\python.exe docker_manage.py status
.\.venv\Scripts\python.exe docker_manage.py stop
```

구성 파일: `Dockerfile`, `compose.yaml`(웹), `compose.gpu.yaml`(GPU 추가).
다른 포트를 쓰려면 실행 전에 `$env:B2_DOCKER_PORT='원하는 포트번호'`를 지정합니다.

도커의 컨테이너를 삭제하거나 서비스를 종료해도 `docker-data` 폴더는 남습니다.
최신 백업이 필요할 때는 도커 서비스를 종료한 뒤 해당 폴더 전체를 복사하십시오.
원본 DB를 다시 가져오려면 도커 종료 후 기존 `docker-data`를 다른 이름으로 보관하고 다시 실행합니다.
기존 도커 데이터에 원본 DB를 덮어쓰지 마십시오.
