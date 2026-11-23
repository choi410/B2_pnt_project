-- PNT 회의록 서비스 · 2단계: 로그인·권한용 employees 테이블 정리
-- Supabase 대시보드 > SQL Editor에서 [A] → [B] → [C] 순서로 실행합니다. 여러 번 실행해도 안전합니다.

-- [A] 확인: 직원 5명이 모두 Supabase Auth 계정과 연결되어 있는지
--     auth_email이 비어 있거나 confirmed가 false인 행은 Authentication > Users에서 계정을 만들거나 확인해야 합니다.
select e.id, e.emp_no, e.name, e.role, e.account_status, e.email,
       u.email as auth_email,
       u.email_confirmed_at is not null as confirmed,
       u.last_sign_in_at
from public.employees e
left join auth.users u on u.id = e.auth_user_id
order by e.id;


-- [B] 서비스 내부 사용자 ID 연결 + 값 제한
--     지금 서비스는 사람을 team1~team4 ID로 기록합니다(회의록 작성자, 프로젝트 PM 등).
--     기존 데이터를 그대로 쓰기 위해 employees에 그 ID를 저장할 칸을 추가합니다.
alter table public.employees add column if not exists app_user_id text;

update public.employees set app_user_id = case emp_no
  when 'E001' then 'admin'
  when 'T001' then 'team1'
  when 'T002' then 'team2'
  when 'T003' then 'team3'
  when 'T004' then 'team4'
  else app_user_id end
where app_user_id is null;

create unique index if not exists employees_app_user_id_key  on public.employees (app_user_id);
create unique index if not exists employees_auth_user_id_key on public.employees (auth_user_id);

-- 역할은 세 가지만 허용 (admin=관리자, pm=PM, member=팀원)
alter table public.employees drop constraint if exists employees_role_check;
alter table public.employees add  constraint employees_role_check
  check (role in ('admin', 'pm', 'member'));

-- 계정 상태: active=사용, inactive=비활성(로그인 차단). 다른 값을 쓰고 있다면 목록에 추가하세요.
alter table public.employees drop constraint if exists employees_account_status_check;
alter table public.employees add  constraint employees_account_status_check
  check (account_status in ('active', 'inactive'));


-- [C] 보안: 브라우저에서 anon/로그인 키로 직접 조회할 때는 "내 행"만 보이게
--     FastAPI 백엔드는 DB 연결 문자열(postgres 계정)로 접속하므로 이 정책의 영향을 받지 않습니다.
alter table public.employees enable row level security;

drop policy if exists "employees read own row" on public.employees;
create policy "employees read own row" on public.employees
  for select to authenticated
  using (auth_user_id = auth.uid());

-- 결과 확인
select id, emp_no, name, role, account_status, app_user_id from public.employees order by id;
