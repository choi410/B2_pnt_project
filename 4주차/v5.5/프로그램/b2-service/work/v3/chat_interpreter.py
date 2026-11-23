"""A bounded language interpreter. It proposes read operations, never answers or SQL.

Database identities, access checks, dates, arithmetic and reference resolution
remain server owned. This module can be evaluated/replaced independently of RAG.
"""
from copy import deepcopy
import json
import re
import sys
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from work.v3 import question_policy as policy, metadata_questions
from work.v3.query_intent import compact, metadata_plan
from work.v17 import questions


class Plan(BaseModel):
    model_config = ConfigDict(extra='forbid')
    action: Literal['projects','project_count','project_order','owner','owner_projects',
                    'meetings','meeting_count','meeting_order','change_rank','changes','search','clarify','social']
    scope: Literal['all','named','previous','results','others'] = 'all'
    projects: list[str] = Field(default_factory=list, max_length=8)
    selection: int = Field(default=0, ge=0, le=100)
    person: str = Field(default='', max_length=80)
    exclude_person: bool = False
    period: str = Field(default='', max_length=80)
    basis: Literal['default','meeting_date','registered_at','created_at'] = 'default'
    order: Literal['newest','oldest'] = 'newest'
    limit: int = Field(default=0, ge=0, le=100)
    group: Literal['none','month','project'] = 'none'
    topic: str = Field(default='', max_length=100)
    unresolved: str = Field(default='', max_length=150)


def infer(w, payload):
    """Caller holds the same AI lock used by document analysis and RAG."""
    import workspace_ai as runtime
    model_dir = w.ROOT.parent/'b2-model'
    if str(model_dir) not in sys.path: sys.path.insert(0, str(model_dir))
    from runtime import load_base, encode_prompt
    import torch
    from lmformatenforcer import JsonSchemaParser
    from lmformatenforcer.integrations.transformers import build_token_enforcer_tokenizer_data, build_transformers_prefix_allowed_tokens_fn
    if runtime._model is None: runtime._tokenizer, runtime._model = load_base()
    system = """Classify a Korean project-service request. Output JSON only; do NOT answer the question.
action: projects=list projects; project_count=count projects; project_order=first/latest created project; owner=who is project PM; owner_projects=projects managed by a person; meetings=list meetings; meeting_count=how many meetings; meeting_order=first/latest meeting; change_rank=project with most change records; search=meeting content, specifications, reasons; repeat=keep previous action for a correction; clarify=unsupported or unclear; social=casual reaction/thanks with no information request.
relation: new=independent question; continue=same project/topic; correct=replace a mistaken condition; others=other projects excluding previous results; subset=choose/filter previous results.
unresolved: true only for unsupported filters (team/status/production date) or vague criteria (most problematic/most talk). Do not mark true just because facts/PM names are absent: server will look them up.
Names, dates, ordinals and counts are resolved by the server, never by you. For 'who is responsible', select owner, not owner_projects. 'How many times did we meet' is meeting_count. A short correction with no new task is repeat/correct. Questions following a PM lookup about that person's other projects are owner_projects/others.
The current entity follows the previous action unless the user explicitly changes it: after meetings, 'the latest one' is meeting_order, never projects. A person's name followed by PM and a request for their projects is owner_projects. A reaction without an information request is social, not projects.
Examples:
등록된 사업을 알려주세요 -> projects/new/false
바람 사업 책임자는 누구지 -> owner/new/false
앞 목록의 세번째 PM -> owner/subset/false
저 담당자가 맡은 나머지도 -> owner_projects/others/false
바람에서 회의를 몇차례 했니 -> meeting_count/new/false
그거 말고 구름으로 (previous action owner) -> repeat/correct/false
우리 부서 것만 -> clarify/continue/true
여러 개를 맡고 있구나 -> social/continue/false
changes=show the actual change-history records/details, not the project inventory. After change_rank, a request for those records/details is changes/continue. Distinguish the winning result projects from all projects compared.
Output keys action, relation, unresolved."""
    state=payload.get('previous',{})
    mode_action={'project_owner':'owner','project_list':'projects','project_order':'project_order','meeting_lookup':'meetings','change_rank':'change_rank','change_history':'changes','count':state.get('action','meeting_count')}
    last={'action':mode_action.get(state.get('mode'),state.get('mode','')),'query':state.get('query',''),
          'project_count':len(state.get('projects',[])),'person_count':state.get('person_count',0)}
    messages=[{'role':'system','content':system},
              {'role':'user','content':json.dumps({'previous':last,'question':payload['question']},ensure_ascii=False)}]
    ids=encode_prompt(runtime._tokenizer,messages).to('cuda')
    if ids.shape[1]>3900: raise ValueError('planning_context_too_large')
    if not hasattr(runtime,'_question_token_data'):
        runtime._question_token_data=build_token_enforcer_tokenizer_data(runtime._tokenizer)
    schema={'type':'object','properties':{
        'action':{'type':'string','enum':list(Plan.model_fields['action'].annotation.__args__)+['repeat']},
        'relation':{'type':'string','enum':['new','continue','correct','others','subset']},
        'unresolved':{'type':'boolean'}},'required':['action','relation','unresolved'],'additionalProperties':False}
    allowed=build_transformers_prefix_allowed_tokens_fn(runtime._question_token_data,JsonSchemaParser(schema))
    with torch.inference_mode():
        output=runtime._model.generate(input_ids=ids,attention_mask=torch.ones_like(ids),do_sample=False,
            max_new_tokens=80,max_time=8,pad_token_id=runtime._tokenizer.eos_token_id,prefix_allowed_tokens_fn=allowed)
    text=runtime._tokenizer.decode(output[0,ids.shape[1]:],skip_special_tokens=True)
    raw=json.loads(text)
    action=raw['action'];relation=raw['relation']
    if action=='repeat':action=mode_action.get(state.get('mode'),'clarify')
    proposal=Plan(action=action,scope={'new':'all','continue':'previous','correct':'named','others':'others','subset':'results'}[relation],
                  unresolved='filter' if raw['unresolved'] else '',person='last' if action=='owner_projects' and state.get('person_count')==1 else '').model_dump()
    return proposal


def available(w,c,actor):
    return [p for p in w.all_records(c,'project') if not p.get('deleted_at') and actor['id'] in p['members']]


def social(question):
    q=compact(question)
    if re.fullmatch(r'(?:네|넵|응|알겠어|알겠습니다|좋아|오케이|고마워|고마워요|감사합니다|감사해요|수고했어|고마워고마워)',q):
        return '네, 궁금한 내용이 있으면 이어서 물어보세요.'
    if re.fullmatch(r'(?:안녕|안녕하세요|안녕하세요ai)',q):
        return '안녕하세요. 프로젝트나 회의 내용 중 궁금한 것을 말씀해 주세요.'
    if re.fullmatch(r'(?:(?:고마워|고마워요|그런데|근데))*((?:넌|너는|네|너의)?이름이?뭐야|누구야|누구니)',q):
        return '저는 PNT AI예요. 프로젝트와 회의 기록을 찾아드려요.'
    if not re.search(r'\?|알려|보여|찾아|누구|언제|어디|왜|어떻게|몇|비교',question) and re.fullmatch(r'.{0,35}(?:그렇구나|그랬구나|많네|바쁘겠다|바쁘겠네|맡고있구나)',q):
        return '필요하면 프로젝트별 회의 기록도 비교해 볼 수 있어요.'
    return None


def local_response(question,previous=None):
    """Unsupported read capabilities are explained, not sent to document RAG."""
    if re.search(r'연락처|전화번호|이메일\s*주소',question):
        return clarification('연락처 조회는 아직 지원하지 않아요. 프로젝트에 등록된 PM 이름은 확인할 수 있어요.')
    if re.search(r'(?:우리|저희)\s*(?:팀|부서).*(?:만|거|것)',question):
        return clarification('팀·부서로 프로젝트를 구분하는 조회는 아직 없어요. 프로젝트 이름이나 PM 이름으로 찾아볼까요?')
    if re.search(r'(?:제일|가장).*(?:문제|말)\s*많',question):
        return {**clarification('어떤 기준으로 비교할까요? 변경 기록 수인지, 회의록 수인지 알려주세요.'),'pending_comparison':True}
    if re.search(r'담당자|PM|pm|책임자',question) and re.search(r'회의\s*(?:횟수|건수)|회의.*몇',question):
        return {**clarification('담당자와 회의 건수를 함께 물으셨네요. 먼저 PM을 볼까요, 회의 건수를 볼까요?'),'pending_actions':['owner','meeting_count']}
    if (previous or {}).get('job',{}).get('result',{}).get('pending_actions') and not re.search(r'PM|pm|담당|책임|회의|건수|횟수',question):
        return {**clarification('프로젝트를 바꿔서 볼 수 있어요. PM과 회의 건수 중 어느 것을 먼저 확인할까요?'),'pending_actions':['owner','meeting_count']}
    return None


def memory(w,c,actor,previous):
    """Only record identities and user-supplied query state, no generated facts."""
    ps=available(w,c,actor); by_id={p['id']:p for p in ps}
    old=(previous or {}).get('context',{})
    result=(previous or {}).get('job',{}).get('result',{})
    if (previous or {}).get('state')=='failed':result={}
    if result.get('kind')=='clarification' and old.get('chat_memory'):
        return deepcopy(old['chat_memory'])
    if result.get('mode')=='social':return deepcopy(old.get('chat_memory') or {})
    projects=list(dict.fromkeys(result.get('result_project_ids',[]) or
        [p['id'] for p in result.get('projects',[]) if result.get('kind')=='projects'] or
        [s['project_id'] for s in result.get('sources',[])]))
    ordered_projects=list(projects)
    projects=[pid for pid in projects if pid in by_id]
    scope=[pid for pid in old.get('project_ids',[]) if pid in by_id]
    # Meeting lists retain their displayed order; no page-size clipping here.
    meetings=list(dict.fromkeys(s['meeting_id'] for s in result.get('sources',[]) if s.get('meeting_id')))
    docs=questions.corpus(w,c,list(by_id)); doc_ids={d['meeting_id'] for d in docs}
    ordered_meetings=list(meetings)
    meetings=[mid for mid in meetings if mid in doc_ids]
    owners=list(dict.fromkeys(by_id[pid].get('pm') for pid in projects if by_id[pid].get('pm'))) if result.get('mode')=='project_owner' else []
    return {'project_ids':projects,'scope_ids':scope,'meeting_ids':meetings,'person_ids':owners,
        'ordered_projects':ordered_projects,'ordered_meetings':ordered_meetings,
        'mode':result.get('mode',''),'subject':old.get('subject',''),
        'action':('project_count' if (old.get('retrieval_plan') or {}).get('intent',{}).get('entity')=='project' else 'meeting_count') if result.get('mode')=='count' else '',
        'time_scope':old.get('time_scope') or {},'retrieval_plan':old.get('retrieval_plan'),
        'query':old.get('query') or (previous or {}).get('question','')}


def payload_for(w,c,actor,question,previous,project_id=None):
    ps=available(w,c,actor); state=memory(w,c,actor,previous)
    names={p['id']:p['name'] for p in ps}
    return {'question':question,'selected_project':names.get(project_id,''),
        'projects':[p['name'] for p in ps][:40],
        'previous':{'query':state.get('query','')[:500],'mode':state.get('mode',''),
            'projects':[names[pid] for pid in state.get('project_ids',[]) if pid in names][:20],
            'scope_count':len(state.get('scope_ids',[])),'meeting_count':len(state.get('meeting_ids',[])),
            'person_count':len(state.get('person_ids',[])),'subject':state.get('subject',''),
            'time_scope':state.get('time_scope',{}),'action':state.get('action','')}}


def needs_interpreter(w,c,actor,question,context,previous):
    """Fast positive results remain fast. Explicit ambiguity stays deterministic.

The fallback is used for unresolved record queries or unresolved references;
established content retrieval is not burdened with another model call.
"""
    ps=available(w,c,actor)
    old_result=(previous or {}).get('job',{}).get('result',{})
    if old_result.get('pending_comparison') and re.search(r'회의|변경',question):return True
    record_context=old_result.get('mode') in ('project_owner','project_list','project_order','meeting_lookup','count','change_rank','meeting_comparison') or bool((previous or {}).get('context',{}).get('chat_memory'))
    correction=bool(previous and policy.name_matches(ps,question) and re.match(r'\s*(?:아\s|아니|미안|아\s*미안)',question))
    if correction:return True
    # A correction with both old and new labels may confuse the legacy name
    # matcher. Interpretation can propose the replacement; executor validates it.
    if previous and re.search(r'말고',question) and (previous.get('job',{}).get('result',{}).get('mode')=='project_owner'):
        return True
    if context.get('projects') or context.get('meetings'):return False
    if context.get('meeting_ids'):return False
    if context.get('retrieval_plan'):
        if not context.get('clarify'):return False
        if record_context and re.search(r'목록|건수|언제|최신|최근',question):return True
        return False
    if metadata_plan(context['query'],ps):return False
    # Preserve established positive source/metadata paths and deliberate
    # unsupported-order clarification; do not invoke a model twice per query.
    if not context.get('clarify'):
        selected=[p for p in ps if p['id'] in context.get('project_ids',[])]
        quick=policy.quick_answer(w,c,selected,actor,context['query'],context.get('project_id') or context.get('scope_override'),
            questions_plan(context['query'],questions.corpus(w,c,[p['id'] for p in selected])))
        if quick is not None:return False
    q=question.lower()
    # Bad dates, destructive requests and unsupported filters are not rephrased
    # into unfiltered reads. Existing explicit errors/clarifications survive.
    if re.search(r'삭제|복원|수정해|바꿔줘|등록해|권한|비밀번호',q):return False
    if re.search(r'완료된\s*프로젝트|진행\s*중인\s*프로젝트|생산일|착수일',q):return False
    # A complete content topic is already handled by the source reader.
    from work.v3.dialogue_plan import slots
    delta=slots(question,ps)
    if delta['dates']:
        scope=metadata_questions.query_scope(w,c,ps,{'entity':'meeting','basis':'meeting_date'},question,{})
        if scope.get('message'):return False
    if context.get('clarify'):
        # A missing explicit name must remain a name error. Generic conversational
        # references can otherwise be mistaken for names by the legacy grammar.
        if '프로젝트' in q and re.search(r'일치하는 프로젝트',context['clarify']) and not re.search(r'다른|거기|우리|저희|그중|그쪽',q):return False
        return bool(re.search(r'거기|그쪽|그\s*(?:사람|분)|책임|맡|회의.*(?:언제|몇|횟수)',q) or record_context and re.search(r'언제|최신|최근|앞사람',q))
    if re.search(r'프로젝트|회의록|회의.*(?:몇|언제|횟수)|책임|pm|담당자|맡|그\s*사람|그\s*분',q):
        # Content requests keep their original source-backed pipeline.
        if re.search(r'납기|납품|속도|사양|용량|커버|안건|아젠다|어젠다|왜|이유|변경.*(?:내용|상황|경위)',q):return False
        return True
    return bool(previous and (re.search(r'거기|그쪽|그\s*(?:사람|분)|(?:첫|두|세|네)\s*번째|책임|맡|아까|앞사람',q)
        or record_context and not re.search(r'내용|관련|안건|사양|납기|납품|속도|용량|커버|기간|안전|비용|왜|이유',q)))


def questions_plan(query,docs):
    from work.v3.question_scope import plan_question
    return plan_question(query,docs)


def clarification(message,projects=()):
    return {'kind':'clarification','answerable':False,'message':message,
            'projects':[{'id':p['id'],'name':p['name']} for p in projects],'points':[],'sources':[]}


def execute(w,c,actor,question,raw,previous=None,project_id=None,meeting_id=None):
    plan=Plan.model_validate(raw); ps=available(w,c,actor); by_id={p['id']:p for p in ps}
    from work.v3 import change_queries
    change_context=change_queries.resolve(w,c,actor,question,previous,project_id,meeting_id,force=plan.action=='changes')
    if change_context is not None:
        if change_context.get('clarify'):
            return change_context,clarification(change_context['clarify'],change_context.get('projects',[]))
        return change_context,change_queries.execute(w,c,actor,change_context)
    if plan.action=='changes':
        return {'query':question,'project_ids':[],'label':''},clarification('프로젝트 이름과 확인할 변경 기록을 알려주세요.')
    state=memory(w,c,actor,previous)
    context={'query':question,'project_id':None,'project_ids':[],'subject':'','label':'',
             'meeting_ids':[],'time_scope':{},'scope_override':True,'interpreted':True}
    def stop(message,choices=()):return context,clarification(message,choices)
    if plan.action=='social':
        return context,{'kind':'conversation','mode':'social','answerable':True,'message':'네, 다른 내용도 궁금하면 이어서 물어보세요.','points':[],'sources':[]}
    # Names, ordinals and date slots are mechanically bound from the question.
    # A model may classify an operation; it cannot silently drop an explicit
    # restriction or turn a reference into an invented project name.
    from work.v3.dialogue_plan import slots
    delta=slots(question,ps)
    suffix=re.split(r'말고',question)[-1] if '말고' in question else question
    named=policy.name_matches(ps,suffix)
    if not named:
        # Match literal short project fragments against accessible names only.
        # Multiple matches remain a choice; never silently take the first one.
        labels=[re.sub(r'(?:에서는|에서|은|는|도|만)$','',x) for x in re.findall(r'[가-힣A-Za-z0-9-]+',suffix)]
        generic={'프로젝트','회의록','회의','담당자','책임자','전체','다른','등록','최근','최신','알려줘','보여줘','누구','목록','사람','이름','당담자'}
        named=[p for p in ps if any(len(x)>=2 and x not in generic and compact(x) in compact(p['name']) for x in labels)]
    ordinals=re.findall(r'(첫|두|둘|세|셋|네|넷|다섯|[1-9]\d*)\s*번째',suffix)
    if ordinals:
        n=ordinals[-1];plan.selection=int(n) if n.isdigit() else {'첫':1,'두':2,'둘':2,'세':3,'셋':3,'네':4,'넷':4,'다섯':5}[n]
        plan.projects=[];plan.scope='results'
        if (state.get('retrieval_plan') or {}).get('group_by'):
            return stop('묶음의 순서인가요, 회의록의 순서인가요? 회의록 제목을 알려주세요.')
    elif named:
        # Keep unknown explicit names for validation instead of discarding them.
        if not plan.projects:plan.projects=[p['id'] for p in named];plan.scope='named'
        if len(named)>1 and len(plan.projects)==1 and plan.projects[0] in [p['id'] for p in named]:
            return stop('어느 프로젝트를 말씀하시나요?',named)
    has_global=bool(re.search(r'전체|모든|각\s*프로젝트|프로젝트별|전부',question))
    people={p['id']:p for p in w.all_records(c,'person')}
    named_people=[p['name'] for p in people.values() if p['name'] in question and any(x.get('pm')==p['id'] for x in ps)]
    if named_people and not named and plan.action in ('projects','owner_projects'):
        # A registered PM name is an explicit filter even if the classifier
        # selects the generic project-list operation.
        plan.action='owner_projects';plan.scope='all';plan.person=named_people[0] if len(named_people)==1 else ''
    if plan.action=='owner_projects' and previous and not named and re.search(r'다른|나머지|그\s*밖',question) and state.get('project_ids'):
        # An explicit exclusion is a server-owned condition, even when the
        # classifier calls it a continuation instead of an "others" request.
        plan.scope='others'
        if not plan.person and len(state.get('person_ids',[]))==1:plan.person='last'
    if named and not named_people and re.search(r'PM|pm|담당자|책임자',question) and re.search(r'누구|누가|각각',question):
        plan.action='owner';plan.person='';plan.exclude_person=False
    if previous and not named and not ordinals and not has_global and plan.action in ('owner','meetings','meeting_count'):
        if len(state.get('project_ids',[]))==1:
            plan.scope='results';plan.projects=[]
            if plan.unresolved=='ambiguous':plan.unresolved=''
    if previous and named and '말고' in question and state.get('mode')=='project_owner' and not re.search(r'회의|목록|개수|몇|변경|사양|납기',suffix):
        plan.action='owner'
        plan.person='';plan.exclude_person=False
    if previous and named and re.match(r'\s*(?:아\s|아니|미안|아\s*미안)',question) and not re.search(r'회의|목록|개수|몇|변경|사양|납기|PM|pm',suffix):
        old_action={'project_owner':'owner','meeting_lookup':'meetings','count':state.get('action','meeting_count')}.get(state.get('mode'))
        if old_action:plan.action=old_action;plan.person='';plan.scope='named'
    if plan.action in ('meetings','meeting_count') and re.search(r'몇\s*(?:번|차례|회|건)|횟수',question):
        plan.action='meeting_count'
    if previous and delta['direction'] and not re.search(r'프로젝트',question) and state.get('mode')=='meeting_lookup':
        # Order is an operation on the entity already being viewed, not a new
        # project inventory. Dates and scope remain grounded in that lookup.
        plan.action='meeting_order';plan.scope='results';plan.person=''
    pending_comparison=(previous or {}).get('job',{}).get('result',{}).get('pending_comparison')
    if pending_comparison and re.search(r'회의|변경',question) and not named:
        plan.scope='results' if state.get('project_ids') else 'all'
        plan.action='meetings' if '회의' in question else 'change_rank'
        plan.unresolved=''
    if not plan.period and delta['dates']:plan.period=' '.join(delta['dates'])
    if delta['basis']:plan.basis=delta['basis']
    if delta['direction']:plan.order=delta['direction']
    if delta['limit'] is not None:plan.limit=min(delta['limit'],100)
    if delta['group']:plan.group=delta['group']
    if plan.unresolved or plan.action=='clarify':
        labels={'filter':'요청한 조건을 현재 등록 정보에서 어떻게 구분할지 알려주세요.',
                'ambiguous':'어느 대상이나 기준을 뜻하는지 조금만 더 알려주세요.',
                'unsupported':'현재는 프로젝트·PM·회의 기록을 조회할 수 있어요.'}
        return stop(labels.get(plan.unresolved,'어떤 기준으로 확인할까요? 프로젝트나 궁금한 항목을 알려주세요.'))
    if plan.action!='search' and re.search(r'삭제|복원|수정|생산일|착수일|완료된|진행\s*중|우리\s*팀|위험|문제\s*많|말\s*많|적절',question):
        return stop('그 조건은 현재 조회 정보만으로 구분하기 어려워요. 프로젝트 목록·PM·회의 기록 중 무엇을 확인할까요?')
    if plan.action!='search' and plan.topic:
        return stop('내용 조건이 있는 질문이네요. 회의 내용을 찾을지, 기록 개수를 셀지 알려주세요.')
    if plan.action!='search' and delta['exclude_date']:
        return stop('제외할 기간과 조회할 항목을 함께 알려주세요.')
    selected=ps
    if project_id:selected=[w.project(c,project_id,actor)]
    elif plan.projects:
        selected=[]
        for label in plan.projects:
            if label in {p['id'] for p in named}:
                found=[by_id[label]]
            else:
                if not compact(label) or compact(label) not in compact(question):return stop('프로젝트 이름을 한 번만 더 알려주세요.')
                found=policy.name_matches(ps,label)
                if not found and len(compact(label))>=2:
                    found=[p for p in ps if compact(label) in compact(p['name'])]
            if not found:return stop('열람 가능한 프로젝트에서 그 이름을 찾지 못했어요. 이름이나 코드를 확인해 주세요.')
            if len(found)>1:return stop('이 이름에 해당하는 프로젝트가 여러 개예요. 어느 프로젝트인가요?',found)
            selected.extend(found)
        selected=list({p['id']:p for p in selected}.values())
    elif plan.scope=='named':return stop('어느 프로젝트를 말씀하시나요?',ps)
    elif plan.scope in ('previous','results','others'):
        # Continue from the result of a ranking, not every compared project.
        ids=state.get('scope_ids',[]) if plan.scope=='previous' and state.get('mode') not in ('change_rank','project_order','change_history','meeting_comparison') else state.get('project_ids',[])
        if not ids:return stop('이어서 볼 프로젝트를 먼저 알려주세요.',ps)
        selected=[p for p in ps if (p['id'] not in ids if plan.scope=='others' else p['id'] in ids)]
    if plan.selection:
        if state.get('mode')=='meeting_lookup':
            mids=state.get('ordered_meetings',[])
            if plan.selection>len(mids):return stop('앞 목록에서 그 순서의 회의록을 찾지 못했어요.')
            meeting_id=mids[plan.selection-1]
            if meeting_id not in state.get('meeting_ids',[]):return stop('그 회의록은 현재 열람할 수 없어요.')
        else:
            ids=state.get('ordered_projects',[])
            if plan.selection>len(ids):return stop('앞 목록에서 그 순서의 프로젝트를 찾지 못했어요.')
            if ids[plan.selection-1] not in by_id:return stop('그 프로젝트는 현재 열람할 수 없어요.')
            selected=[by_id[ids[plan.selection-1]]]
    ids=[p['id'] for p in selected]
    if plan.action=='owner_projects':
        if len(named_people)==1:plan.person=named_people[0]
        if re.search(r'(?:이|가)?\s*(?:PM|pm|담당자)?\s*(?:아닌|아니고)',question):plan.exclude_person=True
        owner_ids=state.get('person_ids',[]) if plan.person=='last' else [pid for pid,p in people.items()
            if p['name']==plan.person and compact(plan.person) in compact(question) and any(x.get('pm')==pid for x in ps)]
        if len(owner_ids)!=1:return stop('어느 담당자를 말씀하시나요? 이름을 알려주세요.')
        uid=owner_ids[0]
        if uid not in people:return stop('담당자 정보를 다시 확인해 주세요.')
        selected=[p for p in selected if (p.get('pm')!=uid if plan.exclude_person else p.get('pm')==uid)]
        ids=[p['id'] for p in selected]
        context['person_id']=uid
    elif plan.person or plan.exclude_person:return stop('담당자 조건을 어떤 항목에 적용할지 알려주세요.')
    context.update(project_ids=ids,project_id=ids[0] if len(ids)==1 else None,
        label=' · '.join(p['name'] for p in selected) if len(selected)<=2 else f'{len(selected)}개 프로젝트')
    if plan.action=='owner' and len(selected)>1 and plan.scope!='all' and not policy.is_broad(question):
        return stop('어느 프로젝트의 PM을 확인할까요?',selected)
    comparison=bool(re.search(r'회의.*(?:많|적|비교)',question) or
        (previous or {}).get('job',{}).get('result',{}).get('pending_comparison') and '회의' in question)
    if comparison:
        if re.search(r'둘\s*중|그\s*중|이\s*중',question):
            selected=[p for p in ps if p['id'] in state.get('project_ids',[])];ids=[p['id'] for p in selected]
            context.update(project_ids=ids,project_id=ids[0] if len(ids)==1 else None)
        if not selected:return stop('비교할 프로젝트를 먼저 알려주세요.',ps)
        if delta['dates']:return stop('기간별 비교는 아직 지원하지 않아요. 전체 기간의 회의록 수로 비교할까요?')
        counts={p['id']:len(questions.corpus(w,c,[p['id']])) for p in selected}
        most=(min if '적' in question else max)(counts.values())
        winners=[p['id'] for p in selected if counts[p['id']]==most]
        return context,{'kind':'metadata','mode':'meeting_comparison','answerable':True,
            'message':'등록된 회의록 수로 비교했어요.','points':[{'project_id':p['id'],'project_name':p['name'],
                'text':f'회의록 {counts[p["id"]]}건','sources':[]} for p in sorted(selected,key=lambda p:counts[p['id']],reverse='적' not in question)],
            'sources':[],'result_project_ids':winners,'count':most,
            'notice':'전체 기간 · 등록된 회의록 수 기준 · 휴지통 제외. 회의 빈도나 실제 업무량을 평가한 결과는 아닙니다.'}
    is_project=plan.action in ('projects','project_count','project_order','owner','owner_projects','change_rank')
    operation={'project_count':'count','meeting_count':'count','project_order':'rank','meeting_order':'rank','owner':'owner','change_rank':'change_rank'}.get(plan.action,'list')
    basis=plan.basis if plan.basis!='default' else ('created_at' if is_project else 'meeting_date')
    if is_project and basis!='created_at':return stop('프로젝트 순서는 서비스 생성일 기준으로 확인할 수 있어요.')
    if not is_project and basis=='created_at':return stop('회의일과 회의록 등록일 중 어느 날짜로 볼까요?')
    intent={'entity':'project' if is_project else 'meeting','operation':operation,'basis':basis,
        'direction':plan.order,'limit':plan.limit or None,'per_project':(plan.scope=='all' or policy.is_broad(question)) if plan.action=='owner' else plan.group=='project','period':None}
    scope={}
    if plan.period:
        if compact(plan.period) not in compact(question):return stop('조회할 기간을 다시 알려주세요.')
        scope=metadata_questions.query_scope(w,c,selected,intent,plan.period+' 회의록 목록',{})
        if scope.get('message'):return stop(scope['message'])
    elif plan.scope in ('previous','results','others') and not is_project:
        scope=deepcopy(state.get('time_scope') or {})
    if plan.action in ('owner','owner_projects','change_rank') and (scope.get('start') or scope.get('end') or plan.limit or plan.group!='none'):
        return stop('이 조회는 현재 등록 정보 전체 기준이에요. 기간·묶음·개수 조건 없이 확인할까요?')
    if meeting_id:
        docs=questions.corpus(w,c,ids)
        doc=next((d for d in docs if d['meeting_id']==meeting_id),None)
        if not doc:return stop('그 회의록은 현재 열람할 수 없어요.')
        scope['meeting_ids']=[meeting_id]
        ids=[doc['project_id']];selected=[by_id[ids[0]]]
        context.update(project_id=ids[0],project_ids=ids,meeting_ids=[meeting_id])
    context['time_scope']={k:scope.get(k) for k in ('mode','start','end')}
    if plan.action=='search':
        allowed_text=compact(question+' '+state.get('subject',''))
        if plan.topic and compact(plan.topic) not in allowed_text:return stop('어떤 항목을 이어서 확인할까요?')
        topic=plan.topic or state.get('subject','') if plan.scope in ('previous','results','others') else plan.topic
        query=(topic+'에 대해, ' if topic and compact(topic) not in compact(question) else '')+question
        context.update(query=query,subject=topic)
        return context,None
    result=metadata_questions.answer(w,c,selected,intent,scope)
    result['group_by']=None if plan.group=='none' else plan.group
    if plan.action=='owner_projects':
        name=people[context['person_id']]['name']
        result['message']=('앞서 본 프로젝트 외에, ' if plan.scope=='others' else '')+f'{name} 님이 PM을 {"맡지 않은" if plan.exclude_person else "맡은"} 프로젝트는 {result.get("total_count",0)}개예요.'
        result['notice']='프로젝트에 등록된 PM 기준 · 열람 가능한 프로젝트만 조회'
    context['retrieval_plan']={'intent':intent,'project_ids':ids,'excluded_ids':[],
        'excluded_periods':[],'time_scope':context['time_scope'],'meeting_ids':context['meeting_ids'],
        'group_by':result.get('group_by')} if plan.action in ('meetings','meeting_count','meeting_order') else None
    return context,result
