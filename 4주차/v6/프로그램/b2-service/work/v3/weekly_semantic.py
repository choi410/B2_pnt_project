"""주간보고 연결의 의미 점수: 메모 줄과 회의록 단위(문장·변경 이력)의 e5 벡터 유사도.

- 회의록 단위 벡터는 rag_store(Supabase pgvector, 연결 실패 시 로컬 sqlite)에 캐시한다.
  AI 대화용 청크와 섞이지 않도록 프로젝트 ID 뒤에 '#weekly'를 붙인 별도 구역에 저장한다.
- 메모 줄 벡터는 매번 계산한다(몇 줄뿐이고 내용이 매번 다르다).
- 검색 모델(torch·e5)이 없거나 오류가 나면 None을 돌려주고, 연결은 지금처럼 낱말 대조만으로 동작한다.
반환값: {row_id: {unit_id: 유사도(코사인)}}
"""
import os,sys

NAMESPACE='#weekly'


def namespace(project_id):
    return str(project_id)+NAMESPACE


def unit_text(unit):
    return str(unit.get('match_text') or unit.get('text') or '').strip()


def unit_key(unit):
    from work.v17.retrieval import fingerprint,MODEL_KEY
    return fingerprint(MODEL_KEY+'\nweekly\n'+unit_text(unit))


def _warn(message):
    print('[weekly-semantic] '+message,file=sys.stderr,flush=True)


def enabled():
    # B2_WEEKLY_SEMANTIC=0 이면 끈다(테스트 기본값). 비어 있으면 켬.
    value=(os.environ.get('B2_WEEKLY_SEMANTIC') or '').strip().lower()
    return value not in ('0','false','off','no')


def semantic_scores(w,index,rows,embed=None):
    if not enabled():return None
    rows=[r for r in rows if str(r.get('text') or '').strip()]
    units=[u for u in index.get('units',[]) if unit_text(u)]
    if not rows or not units:return None
    try:
        import numpy as np
        from work.v17 import rag_store,retrieval
        embed=embed or retrieval.embed
        queries=np.asarray(embed([str(r['text']) for r in rows],'query: '))
    except (ImportError,ValueError,OSError) as exc:
        _warn('검색 모델을 쓸 수 없어 낱말 대조만 사용합니다: '+str(exc)[:160])
        return None
    by_project={}
    for u in units:by_project.setdefault(u['project_id'],[]).append(u)

    def operation(store):
        vectors={}
        for pid,group in by_project.items():
            ns=namespace(pid)
            keys={u['id']:unit_key(u) for u in group}
            wanted=list(dict.fromkeys(keys.values()))
            have=store.vectors(ns,wanted)
            missing=[k for k in wanted if k not in have]
            if missing:
                text_of={keys[u['id']]:unit_text(u) for u in group}
                values=embed([text_of[k] for k in missing],'passage: ')
                rows_to_save=[{'cache_key':k,'vector':v,'passage':{'meeting_id':next(u['meeting_id'] for u in group if keys[u['id']]==k),
                                                                       'title':'weekly','text':text_of[k],'line_ids':[]}}
                              for k,v in zip(missing,values)]
                store.upsert(ns,rows_to_save)
                have.update(zip(missing,values))
            # 지금 회의록에 없는 단위(지운 회의록·바뀐 본문)는 캐시에서 정리한다.
            store.prune(ns,wanted)
            for u in group:vectors[u['id']]=have[keys[u['id']]]
        return store.name,vectors

    try:
        backend,vectors=rag_store.run(w,operation)
    except (ImportError,ValueError,OSError) as exc:
        _warn('회의록 벡터를 만들지 못해 낱말 대조만 사용합니다: '+str(exc)[:160])
        return None
    ids=list(vectors)
    matrix=np.asarray([vectors[i] for i in ids])
    sims=queries@matrix.T
    return {'backend':backend,'scores':{row['id']:{uid:float(s) for uid,s in zip(ids,line)} for row,line in zip(rows,sims)}}
