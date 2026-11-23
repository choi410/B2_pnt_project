"""계정 역할(관리자·PM·팀원) 권한 규칙을 한 곳에 모은다.

두 층으로 나눈다.
  계정 역할   person['role']   admin | pm | member   (Supabase employees.role에서 로그인 때 반영)
  프로젝트 역할 project['pm']   그 프로젝트의 PM 한 명 (기존 코드의 w.project(..., pm=True) 검사가 담당)

규칙
  - 프로젝트 생성: 계정 역할이 pm인 사람만
  - 프로젝트 PM으로 지정: 계정 역할이 pm인 사람만 → 변경이력 수정·삭제·단계 지정 권한이 PM 계정에만 생긴다
  - 프로젝트 삭제·복원·변경이력 수정·검토: 그 프로젝트의 PM만 (기존 검사 유지)
  - 관리자: 업무 데이터(프로젝트·회의록·변경이력·AI) API에 접근하지 않고 설정용 API만 쓴다
  - 관리자·사용 중지 계정은 프로젝트 참여자·담당자 후보에서 뺀다

이름 선택(체험) 로그인처럼 role이 없는 기록은 기존 규칙(level=='leader')을 그대로 따른다.
"""
import re

ADMIN_ALLOWED=re.compile(r'^/api/(?:auth/|admin/|logout$|health$|package-info$)')


def role(person):
 value=(person or {}).get('role')
 if value in ('admin','pm','member'):return value
 return 'pm' if (person or {}).get('level')=='leader' else 'member'


def has_role_data(person):
 return (person or {}).get('role') in ('admin','pm','member')


def is_admin(person):
 return role(person)=='admin'


def admin_path_allowed(path):
 return bool(ADMIN_ALLOWED.match(path or ''))


def can_create_project(person,is_pm_of_any=False):
 if has_role_data(person):return role(person)=='pm'
 # 체험 로그인: 기존 규칙(리더이거나 이미 PM인 프로젝트가 있음)
 return (person or {}).get('level')=='leader' or is_pm_of_any


def assignable(person):
 """프로젝트 참여자·PM·담당자로 고를 수 있는 사람인지."""
 return role(person)!='admin' and (person or {}).get('account_status','active')=='active'


def can_be_project_pm(person):
 if not assignable(person):return False
 return role(person)=='pm' if has_role_data(person) else True


def summary(person):
 """화면 분기용. 실제 차단은 각 API에서 한다."""
 r=role(person)
 return {'role':r,'is_admin':r=='admin','can_open_settings':r=='admin'}
