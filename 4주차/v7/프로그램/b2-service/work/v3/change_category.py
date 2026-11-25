"""Atomic classification of a displayed subject; never approves its content."""
from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from work.v17.change_categories import BASE_CATEGORIES, clean_name, name_key, subject_name


class RecordVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    version: int


class CategoryEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    category: str = Field(min_length=1, max_length=40)
    create: bool = False
    records: list[RecordVersion] = Field(min_length=1, max_length=2000)


def active_events(w, c, project_id):
    meetings = {m['id']: m for m in w.all_records(c, 'meeting')
                if m['project_id'] == project_id and not m.get('deleted_at')}
    return [e for e in w.all_records(c, 'change_event')
            if e['project_id'] == project_id and e['meeting_id'] in meetings
            and not e.get('superseded_by_revision') and e.get('review_state') != '제외'
            and e['source_revision'] == meetings[e['meeting_id']]['revision']
            and not meetings[e['meeting_id']].get('analysis_stale')], meetings


def build_router(w):
    r = APIRouter(prefix='/api/v3')

    @r.patch('/changes/{cid}/category')
    def edit_category(cid: str, body: CategoryEdit, actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            anchor = w.read(c, 'change_event', cid)
            project = w.project(c, anchor['project_id'], actor, True)
            events, meetings = active_events(w, c, project['id'])
            group = [e for e in events if e['category'] == anchor['category']
                     and subject_name(e['title']) == subject_name(anchor['title'])]
            expected = {x.id: x.version for x in body.records}
            if len(expected) != len(body.records) or cid not in {e['id'] for e in group}:
                raise HTTPException(409, '변경 항목이 바뀌었습니다. 최신 목록에서 다시 지정해 주세요.')
            if set(expected) != {e['id'] for e in group}:
                raise HTTPException(409, '이 항목에 기록이 추가되거나 변경되었습니다. 최신 목록에서 다시 지정해 주세요.')
            for e in group:
                w.version(e, expected[e['id']])
                if meetings[e['meeting_id']].get('analysis_state') in ('queued', 'running'):
                    raise HTTPException(409, '관련 회의록 분석이 끝난 뒤 구분을 변경해 주세요.')
            name = clean_name(body.category)
            if not name or len(name) > 20 or name_key(name) in ('전체', '전체구분'):
                raise HTTPException(422, '구분 이름은 전체를 제외한 1~20자로 입력해 주세요.')
            known = [*BASE_CATEGORIES, *project.get('change_categories', []),
                     *[e['category'] for e in events]]
            existing = next((x for x in known if name_key(clean_name(x)) == name_key(name)), None)
            if existing is None and not body.create:
                raise HTTPException(422, '새 구분 추가로 이름을 먼저 지정해 주세요.')
            name = clean_name(existing) if existing is not None else name
            old_category = anchor['category']
            if name == old_category:
                return {'category': name, 'ids': [e['id'] for e in group]}
            # A relabel must not merge two independent visible histories.
            if any(e['id'] not in expected and e['category'] == name
                   and subject_name(e['title']) == subject_name(anchor['title']) for e in events):
                raise HTTPException(409, '이 구분에 같은 이름의 항목이 있습니다. 항목명을 확인한 뒤 변경해 주세요.')
            now = w.now()
            for e in group:
                snapshot = {k: deepcopy(v) for k, v in e.items() if k != 'edit_history'}
                e.setdefault('edit_history', []).append({
                    'at': now, 'by': actor['id'], 'action': '구분 변경', 'record': snapshot})
                # No archive_record(): its review invalidation is for content edits.
                e.setdefault('extracted_category', old_category)
                e.update(category=name, human_edited=True, version=e['version'] + 1,
                         updated_at=now, updated_by=actor['id'])
                w.save(c, 'change_event', e)
            topic_ids = {e.get('topic_id') for e in group if e.get('topic_id')}
            for topic in w.all_records(c, 'change_topic'):
                if topic['project_id'] != project['id'] or topic['id'] not in topic_ids:
                    continue
                if any(e['id'] not in expected and e.get('topic_id') == topic['id'] for e in events):
                    raise HTTPException(409, '같은 대상으로 연결된 다른 항목이 있습니다. 연결 관계를 먼저 확인해 주세요.')
                topic['category'] = name
                w.save(c, 'change_topic', topic)
            if name not in BASE_CATEGORIES:
                project['change_categories'] = list(dict.fromkeys([*project.get('change_categories', []), name]))
            project['version'] = project.get('version', 0) + 1
            w.save(c, 'project', project)
        return {'category': name, 'ids': [e['id'] for e in group]}

    return r
