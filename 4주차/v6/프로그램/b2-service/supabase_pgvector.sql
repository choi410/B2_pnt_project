-- PNT 회의록 서비스 · 의미 검색용 벡터 저장소 (Supabase pgvector)
-- Supabase 대시보드 > SQL Editor에 전체를 붙여 넣고 한 번 실행합니다. 여러 번 실행해도 안전합니다.
-- 임베딩 모델: intfloat/multilingual-e5-small (384차원). 모델을 바꾸면 vector(384)도 바꾸고 테이블을 비운 뒤 다시 색인합니다.

-- 1. pgvector 확장
create extension if not exists vector with schema extensions;

-- 1-1. 예전 안내 SQL(uuid 버전)로 만든 테이블·함수 정리
--      project_id가 text가 아닌 meeting_chunks가 있으면 지웁니다. 청크는 첫 질문 때 자동으로 다시 색인됩니다.
drop function if exists public.match_meeting_chunks(extensions.vector, uuid[], text[], int);
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_schema = 'public' and table_name = 'meeting_chunks'
      and column_name = 'project_id' and data_type <> 'text'
  ) then
    drop table public.meeting_chunks cascade;
  end if;
end $$;

-- 2. 회의록 청크 테이블
--    project_id·meeting_id는 서비스의 uuid4().hex 문자열 ID를 그대로 저장합니다.
--    검색 대상 선정(승인본·기간·권한)은 백엔드가 하고, 이 테이블은 벡터 캐시 + 유사도 계산을 맡습니다.
create table if not exists public.meeting_chunks (
  id            bigint generated always as identity primary key,
  project_id    text not null,
  cache_key     text not null,                       -- sha256(모델키 + 제목 + 청크 본문)
  meeting_id    text not null,
  revision      int  not null default 0,
  review_status text not null default '검토 완료',
  meeting_date  date,
  title         text not null default '',
  line_ids      text[] not null default '{}',        -- 근거 행 ID (L001...)
  content       text not null,
  embedding     extensions.vector(384) not null,
  model_key     text not null,
  created_at    timestamptz not null default now(),
  unique (project_id, cache_key)
);

create index if not exists meeting_chunks_embedding_idx
  on public.meeting_chunks using hnsw (embedding extensions.vector_cosine_ops);
create index if not exists meeting_chunks_meeting_idx
  on public.meeting_chunks (meeting_id, revision);

-- 3. 유사도 검색 함수
--    p_cache_keys: 이번 질문에서 검색해도 되는 청크 목록(백엔드가 만든 코퍼스). 이 밖의 청크는 절대 반환하지 않습니다.
create or replace function public.match_meeting_chunks(
  query_embedding extensions.vector(384),
  p_project_id    text,
  p_cache_keys    text[],
  match_count     int default 20
)
returns table (
  cache_key text, meeting_id text, revision int, title text, meeting_date date,
  line_ids text[], content text, review_status text, similarity float
)
language sql stable
set search_path = public, extensions
as $$
  select c.cache_key, c.meeting_id, c.revision, c.title, c.meeting_date,
         c.line_ids, c.content, c.review_status,
         1 - (c.embedding <=> query_embedding) as similarity
  from public.meeting_chunks c
  where c.project_id = p_project_id
    and c.cache_key = any(p_cache_keys)
  order by c.embedding <=> query_embedding
  limit match_count;
$$;

-- 4. 보안: 브라우저(anon·authenticated 키)에서는 직접 읽거나 쓰지 못하게 막습니다.
--    FastAPI 백엔드는 SUPABASE_DB_URL(데이터베이스 비밀번호 포함)로 접속하므로 영향이 없습니다.
alter table public.meeting_chunks enable row level security;
revoke all on public.meeting_chunks from anon, authenticated;
revoke execute on function public.match_meeting_chunks(extensions.vector, text, text[], int) from public, anon, authenticated;
