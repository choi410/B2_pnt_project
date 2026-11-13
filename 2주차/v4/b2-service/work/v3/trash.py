"""Unified trash and transactional, scoped permanent deletion for V3."""
import json, os
from pathlib import Path
from fastapi import APIRouter,Depends,HTTPException
from work.v17.meeting_purge import Purge,cleanup_files,refers_to,file_values


def records(c):
    return [(r['kind'],r['id'],json.loads(r['payload'])) for r in c.execute('SELECT kind,id,payload FROM records')]


def paths_in(d):
    yield from file_values(d)
    if d.get('original_path'):yield d['original_path']


def deletion_plan(rows,kind,item):
    pid=item['id'] if kind=='project' else item['project_id']
    mids={i for k,i,d in rows if k=='meeting' and (d.get('project_id')==pid if kind=='project' else i==item['id'])}
    targets={(kind,item['id'])}
    if kind=='project':
        targets.update((k,i) for k,i,d in rows if d.get('project_id')==pid or d.get('chosen_project')==pid)
    targets.update((k,i) for k,i,d in rows if k in ('import','change_event') and d.get('meeting_id') in mids)
    # Never orphan a task/report outside the explicitly deleted scope.
    if any((k,i) not in targets and k in ('task','context_draft','report') and any(refers_to(d,mid) for mid in mids) for k,i,d in rows):
        return targets,'연결된 업무 또는 보고서가 있어 영구 삭제할 수 없습니다.'
    ids={i for k,i in targets}
    targets.update((k,i) for k,i,d in rows if k=='notification' and d.get('target_id') in ids)
    affected_topics={d.get('topic_id') for k,i,d in rows if k=='change_event' and (k,i) in targets}
    live_topics={d.get('topic_id') for k,i,d in rows if k=='change_event' and (k,i) not in targets}
    targets.update((k,i) for k,i,d in rows if k=='change_topic' and i in affected_topics-live_topics)
    children=[d for k,i,d in rows if (k,i) in targets]
    if any(d.get('docx') and d.get('preview_finished') is False for d in children):
        return targets,'원본 미리보기 준비가 끝난 뒤 영구 삭제할 수 있습니다.'
    if any(d.get(key) in ('queued','running') and not (d.get('v3_job') and d.get('deleted_at')) for d in children for key in ('analysis_state','change_scan_state','state')):
        return targets,'진행 중인 분석이 끝난 뒤 영구 삭제할 수 있습니다.'
    return targets,''


def build_router(w):
    r=APIRouter(prefix='/api/v3')
    def item_info(c,kind,id,actor):
        d=w.read(c,kind,id);p=d if kind=='project' else w.read(c,'project',d['project_id'])
        if actor['id'] not in p['members'] or actor['id'] not in (p['pm'],d.get('author')):raise HTTPException(403,'접근할 수 없는 항목입니다.')
        if not d.get('deleted_at'):raise HTTPException(409,'휴지통으로 옮긴 뒤 영구 삭제할 수 있습니다.')
        if kind=='meeting' and p.get('deleted_at'):raise HTTPException(409,'프로젝트 휴지통에서 프로젝트 전체를 복원하거나 삭제해 주세요.')
        rows=records(c);targets,blocked=deletion_plan(rows,kind,d)
        if actor['id']!=p['pm']:blocked='프로젝트 PM만 영구 삭제할 수 있습니다.'
        counts={k:sum(t[0]==k for t in targets) for k in ('meeting','change_event','task','report','import')}
        return d,rows,targets,{'id':id,'kind':kind,'title':d.get('title') or d.get('name'),'project_name':p['name'],'deleted_at':d['deleted_at'],'version':d.get('lifecycle_version',1) if kind=='project' else d['version'],'counts':counts,'blocked':blocked}
    @r.get('/trash')
    def trash(actor=Depends(w.user)):
        with w.connect() as c:
            ps={p['id']:p for p in w.all_records(c,'project',include_archived=True) if actor['id'] in p['members']}
            result={'meetings':[],'projects':[]}
            for p in ps.values():
                if p.get('deleted_at') and p['pm']==actor['id']:result['projects'].append(item_info(c,'project',p['id'],actor)[3])
            for m in w.all_records(c,'meeting',include_archived=True):
                p=ps.get(m['project_id'])
                if p and not p.get('deleted_at') and m.get('deleted_at') and actor['id'] in (p['pm'],m['author']):result['meetings'].append(item_info(c,'meeting',m['id'],actor)[3])
            for items in result.values():items.sort(key=lambda d:d['deleted_at'],reverse=True)
            return result
    @r.get('/trash/{kind}/{id}')
    def preview(kind,id,actor=Depends(w.user)):
        if kind not in ('meeting','project'):raise HTTPException(404,'항목을 찾을 수 없습니다.')
        with w.connect() as c:return item_info(c,kind,id,actor)[3]
    @r.delete('/trash/{kind}/{id}')
    def purge(kind,id,body:Purge,actor=Depends(w.user)):
        if kind not in ('meeting','project'):raise HTTPException(404,'항목을 찾을 수 없습니다.')
        staged=[]
        try:
            with w.connect() as c:
                c.execute('BEGIN IMMEDIATE');d,rows,targets,info=item_info(c,kind,id,actor)
                if not body.confirmed:raise HTTPException(422,'영구 삭제 범위를 확인해 주세요.')
                if body.version!=info['version']:raise HTTPException(409,'상태가 바뀌었습니다. 휴지통을 다시 열어 주세요.')
                if info['blocked']:raise HTTPException(409,info['blocked'])
                owned={Path(n).resolve() for k,i,x in rows if (k,i) in targets for n in paths_in(x)}
                shared={Path(n).resolve() for k,i,x in rows if (k,i) not in targets for n in paths_in(x)}
                paths=owned-shared;root=w.FILES.resolve()
                if any(not p.is_relative_to(root) or p==root or p.is_dir() for p in paths):raise HTTPException(409,'파일 저장 경로를 확인해야 합니다. 영구 삭제하지 않았습니다.')
                token=w.uid()
                for index,path in enumerate(sorted(paths)):
                    if path.is_file():
                        target=root/('.purge-'+token+'-'+str(index));os.replace(path,target);staged.append((path,target))
                for k,i in targets:c.execute('DELETE FROM records WHERE kind=? AND id=?',(k,i))
                pid=d['id'] if kind=='project' else d['project_id']
                if c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='rag_vectors'").fetchone():c.execute('DELETE FROM rag_vectors WHERE project_id=?',(pid,))
                if staged:w.save(c,'purge_cleanup',{'id':token,'paths':[str(p) for _,p in staged]})
        except Exception as exc:
            for source,target in reversed(staged):os.replace(target,source)
            if isinstance(exc,OSError):raise HTTPException(409,'파일이 사용 중이어서 삭제하지 못했습니다. 원본 문서를 닫고 다시 시도해 주세요.') from exc
            raise
        cleanup_files(w)
        return {'ok':True}
    return r
