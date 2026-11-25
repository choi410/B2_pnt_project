"""Internal team decisions, activity history, and personal updates."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

LABELS = {'stage': '진행 단계 변경', 'source': '회의록 정정', 'trash': '회의록 휴지통 이동',
          'undo': '변경 항목 확인 취소', 'exclude': '변경 항목 제외'}


def require_lead(p, actor):
    if actor.get('level') != 'leader' or actor.get('department') != p.get('department', actor.get('department')):
        raise HTTPException(403, '담당 팀장만 처리할 수 있습니다.')


def protected(w, c, m):
    if m.get('approved_revision') or any(
        a['meeting_id'] == m['id'] for a in w.all_records(c, 'approval_request')
    ):
        return True
    return m.get('analysis_state') == 'ready' and not any(
        e['meeting_id'] == m['id'] and e.get('source_revision') == m['revision']
        and not e.get('superseded_by_revision') and e.get('review_state') not in ('확인됨', '제외')
        for e in w.all_records(c, 'change_event')
    )


def meeting_permission(w, c, p, m, actor):
    if actor.get('level') == 'leader':
        require_lead(p, actor)
    elif m['author'] != actor['id'] or protected(w, c, m):
        raise HTTPException(403, '팀장에게 처리 요청을 보내 주세요.')


def reason_required(reason):
    if not reason.strip():
        raise HTTPException(422, '처리 사유를 입력해 주세요.')


def record(w, c, p, label, actor, *, mid=None, title='', detail='', reason='', kind='edit',
           recipients=(), request_id=None, retain=False, at=None, event_id=None):
    row = {'id': event_id or w.uid(), 'at': at or datetime.now(w.KST).isoformat(), 'project_id': p['id'],
           'project_name': p['name'], 'meeting_id': mid, 'title': title or p['name'],
           'label': label, 'actor': actor, 'detail': detail, 'reason': reason, 'kind': kind,
           'recipients': list(recipients), 'request_id': request_id}
    if retain:
        row['former_members'] = list(p['members'])
    w.save(c, 'management_event', row)
    return row


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: str
    project_id: str
    target_id: str
    reason: str = Field(min_length=1, max_length=500)
    stage: str = Field(default='', max_length=40)
    title: str = Field(default='', max_length=240)
    date: str = ''
    source: str = Field(default='', max_length=60000)


class Decision(BaseModel):
    approved: bool
    reason: str = Field(default='', max_length=500)


class ReviewVersion(BaseModel):
    id: str
    version: int


class BulkUndo(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    items: list[ReviewVersion] = Field(min_length=1)


def validate_resolved_change(item, meeting, action):
    allowed = ('확인됨', '제외') if action == 'undo' else ('확인됨',)
    if (item.get('review_state') not in allowed or item.get('source_revision') != meeting['revision']
            or meeting.get('analysis_stale') or item.get('superseded_by_revision')
            or meeting.get('analysis_state') in ('queued', 'running')):
        raise HTTPException(409, '현재 회의록의 변경 기록을 다시 확인해 주세요.')


def target(w, c, p, action, tid):
    kind = 'change_event' if action in ('undo', 'exclude') else 'meeting'
    if action == 'stage' and tid == p['id']:
        return p, None
    item = w.read(c, kind, tid)
    if item.get('project_id') != p['id']:
        raise HTTPException(404, '항목을 찾을 수 없습니다.')
    meeting = item if kind == 'meeting' else w.read(c, 'meeting', item['meeting_id'])
    from work.v17.intake_review import active
    active(meeting)
    if kind == 'change_event':
        validate_resolved_change(item, meeting, action)
    return item, meeting


def signature(item, meeting):
    return [item.get('version'), item.get('stage_manual'), item.get('stage_manual_at'),
            item.get('stage_set_at'), meeting.get('revision') if meeting else None]


def build_router(w):
    router = APIRouter(prefix='/api/v3/management')

    def visible(c, actor, kind):
        projects = {p['id']: p for p in w.all_records(c, 'project', include_archived=True)}
        return [r for r in w.all_records(c, kind)
                if actor['id'] in (projects[r['project_id']]['members'] if r['project_id'] in projects
                                  else r.get('former_members', ()))]

    def inbox(c, actor):
        return [r for r in visible(c, actor, 'management_event') if actor['id'] in r['recipients']]

    def summary(row):
        return {k: v for k, v in row.items() if k not in ('proposal', 'recipients', 'former_members', 'snapshot')}

    def links(c, actor):
        meetings = {m['id']: m for m in w.all_records(c, 'meeting') if not m.get('deleted_at')}
        projects = {p['id'] for p in w.all_records(c, 'project') if actor['id'] in p['members']}
        requests = {r['id'] for r in visible(c, actor, 'management_request')
                    if r['requested_by'] == actor['id'] or actor['id'] in r.get('reviewers', ())}
        return lambda r: {'can_open': r.get('meeting_id') in meetings and r['project_id'] in projects,
                          'can_review': r.get('request_id') in requests}

    def seen(c, actor):
        row = c.execute("SELECT 1 FROM records WHERE kind='management_seen' AND id=?", (actor['id'],)).fetchone()
        return w.read(c, 'management_seen', actor['id'])['items'] if row else []

    @router.get('/news')
    def news(actor=Depends(w.user)):
        with w.connect() as c:
            read_ids = set(seen(c, actor))
            rows = sorted(inbox(c, actor), key=lambda r: r['at'], reverse=True)
            people = {p['id']: p['name'] for p in w.all_records(c, 'person')}
            flags = links(c, actor)
        return {'count': sum(r['id'] not in read_ids for r in rows),
                'items': [{**summary(r), **flags(r), 'unread': r['id'] not in read_ids,
                           'person': people.get(r['actor'], '고객' if r['actor'] == 'external' else '')}
                          for r in rows]}

    @router.post('/news/{event_id}/read')
    def read(event_id, actor=Depends(w.user)):
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not any(r['id'] == event_id for r in inbox(c, actor)):
                raise HTTPException(404, '소식을 찾을 수 없습니다.')
            ids = seen(c, actor)
            if event_id not in ids:
                w.save(c, 'management_seen', {'id': actor['id'], 'items': [event_id, *ids]})
        return {'ok': True}

    @router.get('/history')
    def history(project_id: str = '', meeting_id: str = '', kind: str = '',
                offset: int = 0, group_requests: bool = False, actor=Depends(w.user)):
        with w.connect() as c:
            rows = visible(c, actor, 'management_event')
            recorded_ids = {r['id'] for r in rows}
            projects = {p['id']: p for p in w.all_records(c, 'project', include_archived=True)
                        if actor['id'] in p['members']}

            def existing(key, p, at, label, by, mid=None, title='', detail='', category='edit'):
                if at and key not in recorded_ids:
                    rows.append(dict(id=key, at=at, project_id=p['id'], project_name=p['name'],
                                     meeting_id=mid, label=label, actor=by, title=title or p['name'],
                                     detail=detail, reason='', kind=category))

            for p in projects.values():
                for i, e in enumerate(p.get('lifecycle_events', ())):
                    existing(f"project:{p['id']}:{i}", p, e.get('at'),
                             '프로젝트 복원' if e['action'] == 'restore' else '프로젝트 휴지통 이동',
                             e.get('by'), detail=e.get('reason', ''), category='trash')
            for m in w.all_records(c, 'meeting', include_archived=True):
                p = projects.get(m['project_id'])
                if not p:
                    continue
                for i, e in enumerate(m.get('document_events', ())):
                    label = e.get('action', '회의록 수정')
                    category = 'trash' if '휴지통' in label else 'request' if any(
                        word in label for word in ('승인', '검토 요청', '직접 확정', '보완 요청')
                    ) else 'edit'
                    existing(f"document:{m['id']}:{i}", p, e.get('at'), label,
                             e.get('actor'), m['id'], m['title'], e.get('note', ''), category)
                if m.get('deleted_at') and not any(r.get('meeting_id') == m['id'] and r['kind'] == 'trash'
                                                   and r['at'] >= m['deleted_at'] for r in rows):
                    existing(f"trash:{m['id']}", p, m['deleted_at'], '회의록 휴지통 이동',
                             m.get('deleted_by'), m['id'], m['title'], category='trash')
            for a in w.all_records(c, 'approval_request'):
                p = projects.get(a['project_id'])
                if not p:
                    continue
                label = {'smtp': '합의 메일 발송', 'console': '합의 링크 생성'}.get(a.get('delivery_mode'), '합의 요청 기록')
                for key, when, label_text, by, category in (
                    ('sent', a.get('sent_at'), label, a.get('requested_by'), 'mail'),
                    ('reply', a.get('responded_at'), '고객 반려 회신' if a.get('status') == 'rejected' else '고객 합의 회신', 'external', 'mail'),
                    ('apply', a.get('applied_at'), '고객 합의 반영', a.get('applied_by'), 'request'),
                ):
                    existing(f"mail:{a['id']}:{key}", p, when, label_text, by, a['meeting_id'], a.get('title', ''), category=category)
            for e in w.all_records(c, 'change_event'):
                p = projects.get(e['project_id'])
                if not p:
                    continue
                for i, item in enumerate(e.get('edit_history', ())):
                    if item.get('action') != '합의 반영':
                        existing(f"change:{e['id']}:{i}", p, item.get('at'), '변경 항목 ' + item.get('action', '수정'),
                                 item.get('by'), e['meeting_id'], e.get('title', ''))
            people = {p['id']: p['name'] for p in w.all_records(c, 'person')}
            flags = links(c, actor)
            choices = {p['id']: p['name'] for p in projects.values()}
            choices.update({r['project_id']: r['project_name'] for r in rows if r['project_id'] not in choices})
        rows = sorted((r for r in rows if (not project_id or r['project_id'] == project_id)
                       and (not meeting_id or r.get('meeting_id') == meeting_id)),
                      key=lambda r: r['at'], reverse=True)

        def item(row):
            person = people.get(row['actor'], '고객' if row['actor'] == 'external' else '')
            return {**summary(row), **flags(row), 'person': person}

        if group_requests:
            grouped = {}
            for row in rows:
                key = row.get('request_id') or row['id']
                grouped.setdefault(key, []).append(row)
            items = []
            for entries in grouped.values():
                if kind and not any(row['kind'] == kind for row in entries):
                    continue
                latest = item(entries[0])
                if latest.get('request_id'):
                    latest['events'] = [item(row) for row in reversed(entries)]
                items.append(latest)
        else:
            items = [item(row) for row in rows if not kind or row['kind'] == kind]
        offset = max(0, offset)
        return {'items': items[offset:offset+50], 'more': len(items) > offset+50,
                'projects': [{'id': key, 'name': name} for key, name in sorted(choices.items(), key=lambda entry: entry[1])]}

    @router.post('/requests', status_code=201)
    def submit(body: Request, actor=Depends(w.user)):
        from work.v3.service import STAGES
        if body.action not in LABELS:
            raise HTTPException(422, '요청 종류를 확인해 주세요.')
        reason_required(body.reason)
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            p = w.project(c, body.project_id, actor)
            leaders = [person['id'] for person in w.all_records(c, 'person')
                       if person['id'] in p['members'] and person.get('level') == 'leader'
                       and person['department'] == actor['department'] and person['id'] != actor['id']]
            if not leaders:
                raise HTTPException(409, '이 프로젝트의 요청을 받을 팀장이 없습니다.')
            item, m = target(w, c, p, body.action, body.target_id)
            title = item.get('title') or p['name']
            if body.action == 'stage' and body.stage and body.stage not in STAGES:
                raise HTTPException(422, '진행 단계를 확인해 주세요.')
            if body.action == 'source':
                if m.get('analysis_state') in ('queued', 'running'):
                    raise HTTPException(409, '회의록 분석이 끝난 뒤 정정을 요청해 주세요.')
                if len(body.source.strip()) < 10 or not body.title.strip():
                    raise HTTPException(422, '회의 제목과 본문을 입력해 주세요.')
                w.due(body.date)
            if any(r['status'] == 'pending' and r['target_id'] == body.target_id and r['action'] == body.action
                   for r in visible(c, actor, 'management_request')):
                raise HTTPException(409, '같은 항목에 승인 대기 중인 요청이 있습니다.')
            proposal = {k: getattr(body, k) for k in ('stage', 'title', 'date', 'source')}
            row = {'id': w.uid(), 'action': body.action, 'project_id': p['id'], 'target_id': body.target_id,
                   'meeting_id': m['id'] if m else None, 'title': title, 'status': 'pending',
                   'requested_by': actor['id'], 'reason': body.reason.strip(), 'at': w.now(),
                   'snapshot': signature(item, m), 'proposal': proposal, 'reviewers': leaders}
            if body.action == 'stage':
                from work.v3.service import stage_of
                row['before'] = stage_of(m)['stage'] if m else p.get('stage_manual')
            w.save(c, 'management_request', row)
            record(w, c, p, LABELS[body.action] + ' 요청', actor['id'], mid=row['meeting_id'], title=title,
                   reason=row['reason'], kind='request', recipients=leaders, request_id=row['id'])
        return summary(row)

    @router.post('/change-reviews/undo')
    def bulk_undo(body: BulkUndo, actor=Depends(w.user)):
        reason_required(body.reason)
        if len({entry.id for entry in body.items}) != len(body.items):
            raise HTTPException(422, '중복 항목을 제외해 주세요.')
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            for entry in body.items:
                item = w.read(c, 'change_event', entry.id)
                p = w.project(c, item['project_id'], actor)
                require_lead(p, actor)
                w.version(item, entry.version)
                item, meeting = target(w, c, p, 'undo', entry.id)
                item.update(review_state='검토 전', confirmed_by=None, confirmed_at=None,
                            human_edited=True, version=item['version']+1, updated_at=w.now(), updated_by=actor['id'])
                w.save(c, 'change_event', item)
                record(w, c, p, LABELS['undo'], actor['id'], mid=meeting['id'], title=meeting['title'],
                       detail=item['title'], reason=body.reason.strip())
        return {'ok': True}

    @router.get('/requests')
    def requests(actor=Depends(w.user)):
        with w.connect() as c:
            rows = [r for r in visible(c, actor, 'management_request') if
                    r['requested_by'] == actor['id'] or actor['id'] in r.get('reviewers', ())]
        return [summary(r) for r in sorted(rows, key=lambda r: r['at'], reverse=True)]

    @router.get('/requests/{rid}')
    def detail(rid, actor=Depends(w.user)):
        with w.connect() as c:
            row = w.read(c, 'management_request', rid)
            p = w.read(c, 'project', row['project_id'])
            if actor['id'] not in p['members']:
                raise HTTPException(403, '이 프로젝트에 접근할 수 없습니다.')
            if row['requested_by'] != actor['id']:
                require_lead(p, actor)
                if actor['id'] not in row.get('reviewers', ()):
                    raise HTTPException(403, '일부 요청은 요청자와 담당 팀장만 볼 수 있습니다.')
            requester = w.read(c, 'person', row['requested_by'])
            current = None
            if row['action'] == 'source' and row['status'] == 'pending' and not p.get('deleted_at'):
                m = w.read(c, 'meeting', row['meeting_id'])
                current = {key: m.get(key) for key in ('title', 'date', 'source')}
        return {**summary(row), 'label': LABELS[row['action']] + ' 요청', 'requester': requester['name'],
                'proposal': row['proposal'], 'current': current, 'before': row.get('before', row['snapshot'][1])}

    @router.post('/requests/{rid}/decision')
    def decide(rid, body: Decision, actor=Depends(w.user)):
        from work.v3.service import register_revision, begin_reanalysis, run_analysis, stage_of
        if not body.approved:
            reason_required(body.reason)
        job = None
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row = w.read(c, 'management_request', rid)
            p = w.project(c, row['project_id'], actor)
            require_lead(p, actor)
            if actor['id'] not in row.get('reviewers', ()):
                raise HTTPException(403, '담당 팀장만 요청을 처리할 수 있습니다.')
            if row['status'] != 'pending':
                raise HTTPException(409, '이미 처리한 요청입니다.')
            action, data = row['action'], row['proposal']
            if body.approved:
                item, m = target(w, c, p, action, row['target_id'])
                if signature(item, m) != row['snapshot']:
                    raise HTTPException(409, '요청 이후 기록이 바뀌었습니다. 반려 후 다시 요청해 주세요.')
                change = ''
                if action == 'source':
                    before = m['title'] + ' · ' + (m.get('date') or '회의일 미정')
                    if not w.save_content(w, m, actor, data['title'], data['date'], data['source']):
                        raise HTTPException(409, '정정할 내용이 현재 회의록과 같습니다.')
                    change = before + ' → ' + m['title'] + ' · ' + (m.get('date') or '회의일 미정')
                    m.update(analysis_stale=True)
                    register_revision(m)
                    job = (m['id'], begin_reanalysis(w, c, m))
                elif action == 'trash':
                    m.update(deleted_at=w.now(), deleted_by=actor['id'], v3_job=w.uid(), version=m['version']+1)
                    w.save(c, 'meeting', m)
                elif action == 'stage':
                    before = stage_of(m)['stage'] if m else p.get('stage_manual')
                    key = 'stage_manual' if m else 'stage_set'
                    item.update(stage_manual=data['stage'] or None)
                    item.update({key+'_by': actor['id'], key+'_at': w.now()})
                    w.save(c, 'meeting' if m else 'project', item)
                    change = (before or '미지정') + ' → ' + (data['stage'] or '자동 판단')
                else:
                    item.update(review_state='검토 전' if action == 'undo' else '제외',
                                confirmed_by=None if action == 'undo' else actor['id'],
                                confirmed_at=None if action == 'undo' else w.now(), human_edited=True,
                                version=item['version']+1, updated_at=w.now(), updated_by=actor['id'])
                    w.save(c, 'change_event', item)
                record(w, c, p, LABELS[action], actor['id'], mid=row['meeting_id'], title=row['title'],
                       detail=change, reason=row['reason'], kind='trash' if action == 'trash' else 'edit', request_id=rid)
            row.update(status='approved' if body.approved else 'rejected', decided_by=actor['id'],
                       decided_at=w.now(), decision_reason=body.reason.strip())
            w.save(c, 'management_request', row)
            record(w, c, p, LABELS[action] + (' 요청 승인' if body.approved else ' 요청 반려'), actor['id'],
                   mid=row['meeting_id'], title=row['title'], reason=body.reason.strip() or row['reason'],
                   kind='request', recipients=[row['requested_by']], request_id=rid)
        if job:
            w.POOL.submit(run_analysis, w, *job)
        return summary(row)

    return router
