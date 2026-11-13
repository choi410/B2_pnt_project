# B2 프로젝트

주차별 자료와 프로젝트를 정리한 저장소입니다.

| 폴더 | 내용 |
| --- | --- |
| [1주차/v1](1주차/v1/) | 1주차 화면 시안 |
| [1주차/자료정리](1주차/자료정리/) | 기획 문서와 참고 이미지 |
| [1주차/B2-프로젝트](1주차/B2-프로젝트/) | 기존 B2 서비스·AI 모델 코드, 실행 파일, 개발 문서 |
| [2주차/V2](2주차/V2/) | 기존 B2 회의록·업무 관리 v1.7.2 소스와 실행 파일 |
| [2주차/V2/CHOIN](2주차/V2/CHOIN/) | CHOIN 작업본 v1.8.0: 일정·간트차트·변경 이력과 Excel 일정 입출력 |
| [pnt_1112_demo_choin](https://github.com/choi410/B2_pnt_project/tree/choin-demo-1112/pnt_1112_demo_choin) | 11월 12일 CHOIN 시연본 · 회의록·변경 이력과 llama.cpp AI 정리 (전용 브랜치) |

## 최신 B2 서비스 실행

저장소를 내려받은 뒤 기존 버전은 `2주차/V2`, CHOIN 작업본은 `2주차/V2/CHOIN` 폴더에서 실행합니다. Python 3.12 64비트가 필요합니다.

```powershell
git clone --branch v1 https://github.com/choi410/B2_pnt_project.git
cd "B2_pnt_project/2주차/V2/CHOIN"
.\01_처음한번_설치.cmd
.\02_서비스실행.cmd
```

실행 후 <http://127.0.0.1:8771/>에 접속합니다. 내일 다른 PC에서 바로 실행할 때는 [CHOIN 다른 PC 실행 가이드](2주차/V2/CHOIN/다른_PC_실행가이드.md)를 먼저 확인하세요. 전체 기능과 개발 구조는 [CHOIN README](2주차/V2/CHOIN/README.md)에 정리되어 있습니다.

1주차 버전은 [기존 프로젝트 안내](1주차/B2-프로젝트/README.md)와 [기존 도커 안내](1주차/B2-프로젝트/DOCKER_README.md)를 참고하세요.
