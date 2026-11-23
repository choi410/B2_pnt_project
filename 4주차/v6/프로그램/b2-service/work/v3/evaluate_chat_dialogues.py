"""Opt-in end-to-end conversations with real inference and a disposable DB.

Run: python -m work.v3.evaluate_chat_dialogues [report.json]
Never modifies the running service's projects, meetings or chat history.
Add 'holdout' after the report path to run the review-supplied dialogues.
Those cases have now been used during development: they are regressions, not
an unseen accuracy benchmark. Expected clarifications count as passing behavior,
not as successful factual answers; report them separately.
"""
import os,tempfile,json,time,sys
from pathlib import Path
os.environ['B2_TEAM_TESTING']='1'
os.environ['B2_TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='b2-chat-eval-')
from fastapi.testclient import TestClient
from work.v3.server import app,legacy as w
from work.v3.test_questions_trash import project,meeting,event
from work.v3.test_project_order import stamp
from work.v17 import questions


class Inline:
    def submit(self,f,*args):f(*args)


def run():
    w.DB=Path(os.environ['B2_TEAM_DATA_DIR'])/'workspace.sqlite3'
    w.FILES=w.DB.parent/'files';questions.JOBS={};questions.POOL=Inline()
    # Seed files are marked ready explicitly; do not start real analysis jobs.
    class SeedQueue:
        def submit(self,*args):pass
    w.POOL=SeedQueue()
    reports=[]
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        c.post('/api/demo-login',json={'username':'team1'})
        a=project(c,'세척기 교체');b=project(c,'저장탱크 증설');d=project(c,'혼합기 개조')
        secret=project(c,'비공개 배관',members=['team1'])
        for i,p in enumerate((a,b,d)):
            stamp(p,f'2026-01-0{3-i}T09:00:00+09:00')
            with w.connect() as db:
                p=w.read(db,'project',p['id']);p['pm']='team2' if i<2 else 'team3';w.save(db,'project',p)
        meeting(c,a,'세척 노즐은 0.4 MPa로 합의했다.','2026-07-05')
        meeting(c,b,'용량을 20 kL로 합의했다.','2026-07-06')
        meeting(c,b,'용량을 25 kL로 변경 합의했다.','2026-07-20')
        meeting(c,d,'혼합 속도는 30 rpm이다.','2026-05-10')
        meeting(c,d,'혼합 속도는 35 rpm으로 합의했다.','2026-09-01')
        with w.connect() as db:owner_a=w.read(db,'person','team2')['name'];owner_d=w.read(db,'person','team3')['name']
        c.post('/api/demo-login',json={'username':'team2'})
        cases=[
            [('프로젝트 좀 알려줄래','project_list',[a['id'],b['id'],d['id']]),
             ('두 번째 거 책임지는 사람은?','project_owner',[b['id']]),
             ('그 사람 다른 건도 맡아?','project_list',[a['id']])],
            [('혼합기 프로젝트 PM 알려줘','project_owner',[d['id']]),
             ('아 혼합기 말고 탱크','project_owner',[b['id']]),
             ('회의는 언제 했는데?','meeting_lookup',[b['id']])],
            [('세척기 회의 몇 번 했어?','count',1)],
            [('프로젝트 목록 보여줘','project_list',[a['id'],b['id'],d['id']]),
             ('고마워, 근데 넌 이름이 뭐야','social',None),
             ('아까 첫 번째 거 책임자는?','project_owner',[a['id']])],
            [('프로젝트 목록 보여줘','project_list',[a['id'],b['id'],d['id']]),
             ('우리 팀 거만','clarification',None),
             ('제일 말 많았던 데는?','clarification',None)],
            [('지금 프로젝트 뭐뭐 있어?','project_list',[a['id'],b['id'],d['id']]),
             ('첫 번째 말고 세 번째 책임자','project_owner',[d['id']])],
        ]
        if len(sys.argv)>2 and sys.argv[2]=='holdout':
            cases=[
                [(owner_d+' 씨가 맡고 있는 게 뭐였지?','project_list',[d['id']]),
                 ('거기 회의는 자주 했나?','meeting_lookup',[d['id']]),
                 ('제일 최근 건 언제야?','meeting_lookup',[d['id']])],
                [('세척기 담당자랑 회의 횟수 좀','clarification',None),('탱크도 똑같이','clarification',None)],
                [('혼합기 회의 목록, 아니다 건수만','count',2),('아 미안, 세척기였어','count',1),('그럼 목록으로 봐도 돼?','meeting_lookup',[a['id']])],
                [(owner_a+' PM이 하는 프로젝트 다 알려줘','project_list',[a['id'],b['id']]),
                 ('두 개나 하네, 바쁘겠다','social',None),('둘 중에 회의 더 많이 한 쪽은?','meeting_comparison',[b['id']])],
                [('요즘 제일 문제 많은 프로젝트가 어디야?','clarification',None),('그럼 회의 수로','meeting_comparison',[b['id'],d['id']]),
                 (owner_a+' PM 연락처 알아?','clarification',None)],
                [('세척기랑 혼합기 PM 각각 누구야?','project_owner',[a['id'],d['id']]),
                 ('그 사람 다른 것도 해?','clarification',None),('앞사람','clarification',None)],
            ]
        for chain in cases:
            cid=None
            for q,mode,expected in chain:
                started=time.perf_counter()
                response=c.post('/api/conversations/questions',json={'question':q,'conversation_id':cid})
                t=response.json();cid=t.get('id',cid)
                m=t.get('messages',[{}])[-1];r=m.get('result',{})
                actual=r.get('result_project_ids') if isinstance(expected,list) else r.get('count')
                ok=(r.get('kind')=='clarification' if mode=='clarification' else r.get('mode')==mode)
                if expected is not None:ok=ok and (set(actual or [])==set(expected) if isinstance(expected,list) else actual==expected)
                if q=='제일 최근 건 언제야?':ok=ok and len(r.get('sources',[]))==1 and r['sources'][0]['date']=='2026-09-01'
                with w.connect() as db:
                    stored=w.read(db,'ai_message',m['id']) if m.get('id') else {}
                raw=stored.get('job',{}).get('interpreted_plan')
                item={'question':q,'passed':ok,'expected_mode':mode,'mode':r.get('mode',r.get('kind')),
                    'seconds':round(time.perf_counter()-started,2),'route':'model' if raw else 'fast',
                    'message':r.get('message'), 'points':r.get('points'), 'plan':raw,'actual':actual,'expected':expected}
                reports.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    return reports


if __name__=='__main__':
    reports=run()
    summary={'passed':sum(x['passed'] for x in reports),'total':len(reports),
             'clarifications':sum(x['mode']=='clarification' for x in reports),'model_turns':sum(x['route']=='model' for x in reports)}
    print(json.dumps(summary),flush=True)
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps({'summary':summary,'cases':reports},ensure_ascii=False,indent=2),encoding='utf-8')
