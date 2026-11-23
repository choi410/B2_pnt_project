"""Asynchronous chat interpretation using the existing bounded question queue."""
from copy import deepcopy
import time
from fastapi import HTTPException
from work.v17 import questions
from work.v3 import chat_interpreter as language, question_policy as policy
from work.v3.question_scope import plan_question


def start(w,actor,question,previous,project_id=None,meeting_id=None):
    with w.connect() as c:
        ps=language.available(w,c,actor)
        if project_id:w.project(c,project_id,actor)
    with questions.LOCK:
        active=[j for j in questions.JOBS.values() if j['state'] not in ('done','failed')]
        if any(j['user_id']==actor['id'] for j in active):raise HTTPException(409,'이전 답변이 끝나면 이어서 물어봐 주세요.')
        if len(active)>=4:raise HTTPException(429,'질문 처리가 밀려 있어요. 잠시 후 다시 물어봐 주세요.')
        jid=w.uid()
        job={'id':jid,'user_id':actor['id'],'question':question,'state':'queued',
             'scope_ids':[p['id'] for p in ps],'created':time.time()}
        questions.JOBS[jid]=job
    try:questions.POOL.submit(run,w,jid,deepcopy(previous),project_id,meeting_id)
    except Exception:questions.update(jid,state='failed',error='질문을 시작하지 못했어요. 다시 시도해 주세요.')
    with questions.LOCK:return deepcopy(questions.JOBS[jid])


def run(w,jid,previous,project_id,meeting_id):
    started=time.perf_counter()
    with questions.LOCK:job=deepcopy(questions.JOBS[jid])
    try:
        with w.connect() as c:
            actor=w.read(c,'person',job['user_id'])
            payload=language.payload_for(w,c,actor,job['question'],previous,project_id)
        questions.update(jid,state='waiting_model')
        # Do not freeze a conversation behind a long meeting analysis.
        if not w.AI_LOCK.acquire(timeout=3):
            questions.update(jid,state='done',result=language.clarification(
                '지금 회의록을 분석하고 있어 질문의 뜻을 확인하는 데 시간이 걸려요. 잠시 후 같은 질문을 다시 보내 주세요.'),seconds=3)
            return
        try:
            questions.update(jid,state='interpreting')
            raw=language.infer(w,payload)
        finally:w.AI_LOCK.release()
        questions.trace_job(jid,'interpretation',route='model',action=raw.get('action'),scope=raw.get('scope'),
                            unresolved=bool(raw.get('unresolved')),seconds=round(time.perf_counter()-started,2))
        # Refresh all records/permissions after model execution.
        with w.connect() as c:
            actor=w.read(c,'person',job['user_id'])
            context,result=language.execute(w,c,actor,job['question'],raw,previous,project_id,meeting_id)
            context['chat_memory']=language.memory(w,c,actor,previous)
            ids=context['project_ids']
            if result is None:
                projects=[w.project(c,pid,actor) for pid in ids]
                plan=plan_question(context['query'],questions.corpus(w,c,ids))
                scope=context.get('time_scope') or {}
                if scope.get('start') or scope.get('end'):plan.update(scope,message='')
                if context.get('meeting_ids'):plan['meeting_ids']=context['meeting_ids']
                result=policy.quick_answer(w,c,projects,actor,context['query'],True,plan)
        questions.update(jid,scope_ids=ids,conversation_context=context,interpreted_plan=raw)
        if result is not None:
            questions.update(jid,state='done',result=result,seconds=round(time.perf_counter()-started,1))
        else:
            questions.update(jid,question=context['query'],query_plan=plan)
            questions.answer_job(w,jid,policy)
            questions.update(jid,question=job['question'],seconds=round(time.perf_counter()-started,1))
    except HTTPException as exc:questions.update(jid,state='failed',error=str(exc.detail))
    except Exception as exc:
        questions.trace_job(jid,'interpretation_failed',reason=type(exc).__name__)
        questions.update(jid,state='done',result=language.clarification(
            '질문의 뜻을 정확히 확인하지 못했어요. 어느 프로젝트에서 무엇을 확인할지 조금만 더 알려주세요.'),seconds=round(time.perf_counter()-started,1))
