"""Manual same-model benchmark. Reads existing documents, never writes meetings."""
import json,sqlite3,time,sys
from pathlib import Path
from work.v17 import server as w
from work.v17.demo_ai import extract_notes
from work.v17.changes import extract_changes
from work.v3.fast_ai import extract_joint

def main():
    db=w.ROOT/'data/demo/workspace.sqlite3'
    with sqlite3.connect(db) as c:ms=[json.loads(x[0]) for x in c.execute("select payload from records where kind='meeting'")]
    selected=[m for m in ms if m['id'] in ('a648cf3d7a66417c90a61d6def487a23','9e52d521d25e47db844a8640d5170b30','8f31b210b07a41c990fc500aea737d8d')]
    output=[]
    prior=json.loads((w.ROOT/'data/demo/ai-speed-comparison.json').read_text(encoding='utf-8')) if '--joint-only' in sys.argv else []
    import workspace_ai as shared
    sys.path.insert(0,str(w.ROOT.parent/'b2-model'))
    from runtime import load_base
    start=time.perf_counter();shared._tokenizer,shared._model=load_base();print('cold_load_seconds',round(time.perf_counter()-start,2),flush=True)
    for m in selected:
        record=next((x for x in prior if x['title']==m['title']),{'title':m['title'],'source':m['source']})
        for mode in (('joint',) if prior else ('baseline','joint')):
            started=time.perf_counter()
            try:
                if mode=='baseline':
                    notes,measure=extract_notes(m['lines']);changes,cseconds=extract_changes(w,m,[])
                    measure['change_seconds']=cseconds
                else:notes,changes,measure=extract_joint(w,m['lines'],[],use_cache=False)
                record[mode]={'seconds':round(time.perf_counter()-started,2),'notes':notes,'changes':changes,'metrics':measure}
                print(m['title'],mode,record[mode]['seconds'],[(x['title'],x['business_state']) for x in changes['items']],flush=True)
            except Exception as e:record[mode]={'error':str(e)};print(mode,'ERROR',str(e),flush=True)
        output.append(record)
        (w.ROOT/'data/demo/ai-speed-comparison.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
