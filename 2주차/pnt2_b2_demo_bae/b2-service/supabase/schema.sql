-- PNT 회의록 서비스 v4 · Supabase(Postgres) 스키마
-- 서버를 처음 실행하면 자동으로 적용됩니다. Supabase 대시보드의 SQL Editor 에
-- 그대로 붙여 넣어 실행해도 됩니다. 여러 번 실행해도 안전합니다.

-- 프로젝트·회의록·변경이력 등 업무 기록 (종류별 JSON 문서)
create table if not exists public.records(
  kind text not null,
  id text not null,
  payload text not null,
  seq bigint generated always as identity,
  primary key(kind,id)
);

-- 종류별 변경 번호. 서버는 이 번호가 그대로면 이미 읽어 둔 기록을 다시 내려받지 않습니다.
create table if not exists public.record_versions(kind text primary key,version bigint not null);
create or replace function public.b2_bump_record_version() returns trigger
language plpgsql set search_path='' as $$
declare changed text;
begin
  if tg_op='DELETE' then changed:=old.kind; else changed:=new.kind; end if;
  insert into public.record_versions(kind,version) values(changed,1)
  on conflict(kind) do update set version=public.record_versions.version+1;
  return null;
end $$;
drop trigger if exists b2_records_version on public.records;
create trigger b2_records_version after insert or update or delete on public.records
  for each row execute function public.b2_bump_record_version();

-- 사용자 프로필과 역할. 계정(이메일·비밀번호)은 Supabase Auth 의 auth.users 가 관리합니다.
create table if not exists public.profiles(
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null default '',
  name text not null,
  department text not null default '',
  position text not null default '담당자',
  level text not null default 'staff' check (level in ('admin','leader','staff')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

-- 역할별로 허용하는 기능. 관리 화면에서 바꾸면 바로 적용됩니다.
create table if not exists public.role_permissions(
  level text not null check (level in ('admin','leader','staff')),
  permission text not null,
  primary key(level,permission)
);
insert into public.role_permissions(level,permission) values
  ('admin','user.manage'),
  ('admin','project.create'),
  ('admin','project.manage_any'),
  ('leader','project.create')
on conflict do nothing;

create table if not exists public.sessions(token text primary key,user_id text not null,expires double precision not null);
create table if not exists public.login_limits(id text primary key,failures integer not null,last double precision not null);
create table if not exists public.calendar_memos(user_id text not null,day text not null,text text not null,primary key(user_id,day));
create table if not exists public.rag_vectors(project_id text,cache_key text,vector text,primary key(project_id,cache_key));

-- 이 표들은 FastAPI 서버(DB 직접 연결)만 읽고 씁니다. 행 수준 보안을 켜고 정책을
-- 두지 않아, 공개 키로 호출하는 Supabase Data API 에서는 아무 행도 보이지 않습니다.
alter table public.records enable row level security;
alter table public.record_versions enable row level security;
alter table public.profiles enable row level security;
alter table public.role_permissions enable row level security;
alter table public.sessions enable row level security;
alter table public.login_limits enable row level security;
alter table public.calendar_memos enable row level security;
alter table public.rag_vectors enable row level security;
do $$
begin
  if exists(select 1 from pg_roles where rolname='anon') and exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on public.records,public.record_versions,public.profiles,public.role_permissions,public.sessions,
      public.login_limits,public.calendar_memos,public.rag_vectors from anon,authenticated;
  end if;
end $$;

-- Supabase Auth 에 계정이 생기면 프로필을 '담당자'로 자동 생성합니다.
create or replace function public.b2_create_profile() returns trigger
language plpgsql security definer set search_path='' as $$
begin
  insert into public.profiles(id,email,name)
  values(new.id,coalesce(new.email,''),
    coalesce(nullif(new.raw_user_meta_data->>'name',''),nullif(split_part(coalesce(new.email,''),'@',1),''),'사용자'))
  on conflict(id) do nothing;
  return new;
end $$;
drop trigger if exists b2_profile_on_signup on auth.users;
create trigger b2_profile_on_signup after insert on auth.users
  for each row execute function public.b2_create_profile();

-- 이미 만들어 둔 계정의 프로필 보충
insert into public.profiles(id,email,name)
select id,coalesce(email,''),
  coalesce(nullif(raw_user_meta_data->>'name',''),nullif(split_part(coalesce(email,''),'@',1),''),'사용자')
from auth.users
on conflict(id) do nothing;
