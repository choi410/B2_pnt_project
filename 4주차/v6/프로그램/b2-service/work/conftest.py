"""테스트는 개발 PC의 .env(실제 Supabase 로그인·벡터DB 설정)와 분리해서 실행한다.

.env 값은 실제 환경변수가 없을 때만 채워지므로(mailer.load_env), 여기서 빈 값·로컬 값을 먼저 넣어 둔다.
- 기존 테스트는 이름 선택(체험) 로그인을 쓰므로 Supabase 로그인 모드를 끈다.
- 테스트용 회의록이 실제 Supabase meeting_chunks에 저장되지 않도록 벡터 저장소를 sqlite로 고정한다.
- B2_WEEKLY_SEMANTIC=0: 주간보고 연결은 낱말 대조만(실제 검색 모델을 테스트에서 쓰지 않음). 의미 점수 테스트는 따로 켠다.
- B2_CHANGE_APPROVAL=0: 기존 테스트는 PM 승인 없이 검수 결과가 바로 반영되는 규칙을 검증한다. 승인 테스트는 따로 켠다.
- B2_SKIP_DOTENV=1: .env 파일 자체를 읽지 않는다(실제 SMTP 메일 발송 방지).
Supabase 동작이 필요한 테스트(test_auth_supabase, test_permissions)는 각자 가짜 값으로 다시 설정한다.
"""
import os

for key,value in {'B2_SKIP_DOTENV':'1','B2_AUTH_MODE':'','SUPABASE_URL':'','SUPABASE_ANON_KEY':'',
                  'B2_VECTOR_STORE':'sqlite','SUPABASE_DB_URL':'','B2_VECTOR_AUTOSYNC':'0','B2_WEEKLY_SEMANTIC':'0','B2_CHANGE_APPROVAL':'0'}.items():
    os.environ[key]=value


import importlib.util,sys
from pathlib import Path
import pytest

SERVICE=Path(__file__).resolve().parents[1]


def _same(a,b):
    try:return Path(a).resolve()==Path(b).resolve()
    except (OSError,ValueError,TypeError):return False


def _pin_service_server():
    """서비스 코드의 `from server import lines`가 항상 b2-service/server.py를 쓰게 고정한다.

    같은 이름의 work/v17/server.py, work/v3/server.py가 있어 테스트 실행 순서·경로에 따라
    다른 파일이 'server'로 잡히면 "cannot import name 'lines' from 'server'" 오류가 난다.
    """
    if not any(_same(p,SERVICE) for p in sys.path):sys.path.insert(0,str(SERVICE))
    loaded=sys.modules.get('server')
    if loaded is not None and _same(Path(getattr(loaded,'__file__','') or '.').parent,SERVICE):return
    spec=importlib.util.spec_from_file_location('server',SERVICE/'server.py')
    module=importlib.util.module_from_spec(spec)
    sys.modules['server']=module
    try:spec.loader.exec_module(module)
    except (ImportError,OSError):
        # fastapi 등이 없는 환경: 해당 테스트들은 어차피 건너뛰므로 고정하지 않는다.
        sys.modules.pop('server',None)


_pin_service_server()


def pytest_collection_finish(session):
    _pin_service_server()


@pytest.fixture(autouse=True)
def _service_server_module():
    _pin_service_server()
    yield
