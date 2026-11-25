"""Asynchronous chat interpretation using the existing bounded question queue."""
from copy import deepcopy
import time
from fastapi import HTTPException
from work.v17 import questions
from work.v3 import chat_interpreter as language, question_policy as policy
from work.v3.question_scope import plan_question


def start(w,actor,question,previous,project_id=None,meeting_id=None,semantic_past=None,shipment_probe=None,*,definition_term=None):
    with w.connect() as c:
        ps=language.available(w,c,actor) if definition_term is None else []
        if project_id:w.project(c,project_id,actor)
    with questions.LOCK:
        active=[j for j in questions.JOBS.values() if j['state'] not in ('done','failed')]
        if any(j['user_id']==actor['id'] for j in active):raise HTTPException(409,'이전 답변이 끝나면 이어서 물어봐 주세요.')
        if len(active)>=4:raise HTTPException(429,'질문 처리가 밀려 있어요. 잠시 후 다시 물어봐 주세요.')
        jid=w.uid()
        job={'id':jid,'user_id':actor['id'],'question':question,'state':'queued',
             'scope_ids':[p['id'] for p in ps],'created':time.time()}
        questions.JOBS[jid]=job
    try:
        if definition_term is not None:
            questions.POOL.submit(run_definition,w,jid,definition_term)
        elif semantic_past is not None:
            from work.v3.semantic_chat import run as semantic_run
            questions.POOL.submit(semantic_run,w,jid,deepcopy(semantic_past),project_id,meeting_id)
        elif shipment_probe is not None:
            questions.POOL.submit(run,w,jid,deepcopy(previous),project_id,meeting_id,shipment_probe)
        else:questions.POOL.submit(run,w,jid,deepcopy(previous),project_id,meeting_id)
    except Exception:questions.update(jid,state='failed',error='질문을 시작하지 못했어요. 다시 시도해 주세요.')
    with questions.LOCK:return deepcopy(questions.JOBS[jid])


def run_definition(w,jid,term):
    from work.v3.term_definition import answer, known_answer

    started=time.perf_counter()
    if (known:=known_answer(term)) is not None:
        questions.update(jid,state='done',result=known,seconds=0)
        return
    questions.update(jid,state='waiting_model')
    try:
        with w.AI_LOCK:
            questions.update(jid,state='answering')
            result=answer(w,term)
        questions.update(jid,state='done',result=result,seconds=round(time.perf_counter()-started,1))
    except Exception as exc:
        questions.trace_job(jid,'definition_failed',reason=type(exc).__name__)
        questions.update(jid,state='failed',error='용어 설명을 가져오지 못했어요. 다시 물어봐 주세요.')


def run(w,jid,previous,project_id,meeting_id,shipment_probe=None):
    started=time.perf_counter()
    with questions.LOCK:job=deepcopy(questions.JOBS[jid])
    try:
        with w.connect() as c:
            actor=w.read(c,'person',job['user_id'])
            payload=language.payload_for(w,c,actor,job['question'],previous,project_id)
        raw=language.direct_reference(payload)
        route='source_reference' if raw else 'model'
        intent, equipment = None, None
        if raw is None:
            questions.update(jid,state='waiting_model')
            # The background question stays pending until the shared model is free.
            with w.AI_LOCK:
                questions.update(jid,state='interpreting')
                if shipment_probe is not None:
                    prior_shipment,interpret_fallback=shipment_probe
                    try:
                        intent,equipment=language.shipment_intent(w,job['question'],prior_shipment.get('origin_question',''))
                        questions.trace_job(jid,'request_purpose',intent=intent)
                    except Exception as exc:
                        intent='unclear'
                        questions.trace_job(jid,'request_purpose',error=type(exc).__name__)
                    if intent not in ('actual_equipment_shipments','planned_shipments') and interpret_fallback:
                        raw=language.infer(w,payload)
                else:
                    raw=language.infer(w,payload)
        if raw is not None:
            questions.trace_job(jid,'interpretation',route=route,action=raw.get('action'),scope=raw.get('scope'),
                                unresolved=bool(raw.get('unresolved')),seconds=round(time.perf_counter()-started,2))
        # Refresh all records/permissions after model execution.
        with w.connect() as c:
            actor=w.read(c,'person',job['user_id'])
            if intent=='actual_equipment_shipments':
                from work.v3.shipment_evidence import answer
                context,result=answer(w,c,actor,job['question'],equipment,project_id,prior_shipment)
                questions.update(jid,state='done',scope_ids=context['project_ids'],conversation_context=context,
                    result=result,seconds=round(time.perf_counter()-started,1))
                return
            if intent=='planned_shipments':
                result=language.clarification(
                    '출고 예정 물량의 합계는 출고 계획 자료에서 확인할 수 있어요. '
                    '프로젝트를 지정하면 회의록에 기록된 출고 일정이나 계획을 찾아볼 수 있어요.')
                result['mode']='shipment_plan_unavailable'
                questions.update(jid,state='done',scope_ids=[],conversation_context={'query':job['question'],'project_ids':[]},
                    result=result,seconds=round(time.perf_counter()-started,1))
                return
            if raw is None:
                from work.v3.conversations import resolve_question
                context=resolve_question(w,c,actor,job['question'],previous,project_id,meeting_id)
                result=language.clarification(context['clarify'],context.get('projects',[])) if context.get('clarify') else None
            else:
                context,result=language.execute(w,c,actor,job['question'],raw,previous,project_id,meeting_id)
            from work.v3.chat_state import pin_selection
            pin_selection(w,c,actor,context)
            context['chat_memory']=language.memory(w,c,actor,previous)
            ids=context['project_ids']
            if result is None:
                projects=[w.project(c,pid,actor) for pid in ids]
                plan=plan_question(context['query'],questions.corpus(w,c,ids))
                scope=context.get('time_scope') or {}
                if scope.get('start') or scope.get('end'):plan.update(scope,message='')
                if context.get('meeting_ids'):plan['meeting_ids']=context['meeting_ids']
                result=policy.quick_answer(w,c,projects,actor,context['query'],True,plan,
                                           shipment_checked=intent is not None and intent!='unclear')
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
