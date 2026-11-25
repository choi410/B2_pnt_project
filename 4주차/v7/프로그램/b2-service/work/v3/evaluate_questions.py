"""Run fixed synthetic question sets against the real local models in isolation.

python -m work.v3.evaluate_questions --dataset path.json --output result.json
Uses a new temporary DB and uploads folder, never the running service's data.
Mechanical source/date checks are NOT factual answer grading. Compare outputs
against the frozen expected answers separately; keep failures in the report.
"""
import argparse,hashlib,json,os,tempfile,time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--indices',type=int,nargs='*',help='One-based selected questions for regression checks')
    args=parser.parse_args()
    dataset=json.loads(args.dataset.read_text(encoding='utf-8'))
    scratch=Path(tempfile.mkdtemp(prefix='b2-fixed-eval-')).resolve()
    os.environ['B2_TEAM_TESTING']='1'
    os.environ['B2_TEAM_DATA_DIR']=str(scratch)
    os.environ['B2_DEMO_MODE']='1'
    for key in ('B2_DATABASE','B2_AI_DEBUG','B2_SAMPLE_DOCX'):os.environ.pop(key,None)
    from fastapi.testclient import TestClient
    from work.v3.server import app,legacy as w
    from work.v17 import questions
    assert Path(w.DB).resolve().is_relative_to(scratch), 'Refusing a non-isolated database'
    class Deferred:
        def submit(self,*args):pass
    class Inline:
        def submit(self,fn,*args):fn(*args)
    w.POOL=Deferred()  # Registration analysis is irrelevant to raw-text search.
    questions.POOL=Inline()
    report={'dataset':str(args.dataset.resolve()),'dataset_sha256':hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
            'isolated_database':str(w.DB),'grading':'Mechanical checks only; manual factual review required','results':[]}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        c.post('/api/demo-login',json={'username':'team1'}).raise_for_status()
        response=c.post('/api/projects',json={'name':dataset['project'],'members':['team1']})
        response.raise_for_status();pid=response.json()['id']
        for i,meeting in enumerate(dataset['meetings']):
            body=f'회의명: 검증 회의 {i+1}\n회의일: {meeting["date"]}\n프로젝트: {dataset["project"]}\n'+meeting['body']
            uploaded=c.post('/api/v3/imports',files=[('files',('검증.txt',body.encode(),'text/plain'))])
            uploaded.raise_for_status();item=uploaded.json()['items'][0]
            registered=c.post('/api/v3/register',json={'items':[{'id':item['id'],'project_id':pid,'date':meeting['date']}]})
            registered.raise_for_status()
        for i,test in enumerate(dataset['questions']):
            if args.indices and i+1 not in args.indices:continue
            start=time.monotonic()
            response=c.post('/api/questions',json={'project_id':pid,'question':test['question']})
            response.raise_for_status();jid=response.json()['id']
            job=c.get('/api/questions/'+jid).json();result=job.get('result',{})
            proofs=[]
            for source in result.get('sources',[]):
                r=c.get('/api/questions/'+jid+'/sources/'+source['id'])
                proofs.append({'status':r.status_code,'proof':r.json()})
            dates={s.get('date','') for s in result.get('sources',[])}
            checks={'done':job.get('state')=='done','sources_open':all(p['status']==200 for p in proofs)}
            if test.get('max_date'):checks['no_future_sources']=all(d<=test['max_date'] for d in dates)
            if test.get('required_dates'):checks['required_source_dates']=set(test['required_dates'])<=dates
            if 'count' in test:checks['count']=result.get('count')==test['count']
            if 'answerable' in test:checks['answerable']=result.get('answerable')==test['answerable']
            internal=questions.JOBS[jid]
            row={'index':i+1,**test,'seconds':round(time.monotonic()-start,2),'checks':checks,'job':job,
                 'plan':internal.get('query_plan'),'diagnostics':internal.get('diagnostics'),'proofs':proofs}
            report['results'].append(row)
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:row[k] for k in ('index','question','seconds','checks')}|{'state':job.get('state'),
                'error':job.get('error'),'message':result.get('message'),'points':[p['text'] for p in result.get('points',[])]},ensure_ascii=False),flush=True)
    print('Saved: '+str(args.output.resolve()),flush=True)


if __name__=='__main__':main()
