"""Project ownership and history statistics from authorized records, without RAG."""
import re
from work.v3.change_approval import published


def active_changes(w,c,projects):
    """Shared record set for both rankings and their drill-down lists."""
    ids={p['id'] for p in projects}
    meetings={m['id']:m for m in w.all_records(c,'meeting')
              if m['project_id'] in ids and not m.get('deleted_at') and not m.get('analysis_stale')}
    events=[]
    for event in w.all_records(c,'change_event'):
        m=meetings.get(event.get('meeting_id'))
        if not m or event.get('project_id')!=m['project_id']:continue
        if event.get('deleted_at') or event.get('superseded_by_revision') or not published(event,m):continue
        if event.get('source_revision')!=m.get('revision'):continue
        events.append(event)
    return events,meetings


def plan(q):
    # q is normalized and has matched project labels removed. Full consumption
    # prevents task owners, status filters or explanations becoming PM lookups.
    prefix = r'(?:(?:현재|지금|그럼|그러면|우리|저희|전체|모든|각|그|이))*'
    entity = r'프로젝트(?:들)?(?:별|마다)?(?:의|은|는|가|를)?'
    owner = r'(?:총괄담당자|담당자|책임자|pm)(?:가|은|는|이)?'
    ask = r'(?:누구입니까|누구인가요|누구인가|누군가요|누구야|누구지|누구|누가|이름)?(?:알려줘|알려주세요|알려줄래|보여줘|확인해줘)?'
    owns = r'누가(?:담당|관리)(?:해|하나요|하니|하고있어|합니까)'
    if re.fullmatch(prefix+entity+r'(?:'+owner+ask+'|'+owns+')', q):
        return {'entity':'project','operation':'owner','basis':'project_record',
                'direction':'newest','limit':None,'period':None,
                'per_project':bool(re.search(r'전체|모든|각|별|마다', q))}
    if '프로젝트' not in q or not re.search(r'변경이력|변경기록', q):return None
    if not re.search(r'가장|제일|최다|많은프로젝트', q):return None
    # Unsupported dates/status qualifiers are deliberately not discarded.
    words = '''프로젝트 변경이력 변경기록 가장 제일 최다 많은 많아 많나요 많은건 많은것
        현재 지금 전체 모든 중에서 중에 가운데 중 어떤 어디 무슨 뭐야 무엇인가요 누구인가요
        알려줘 알려주세요 알려줄래 보여줘 찾아줘 그럼 그러면 는 은 이 가 을 를 의 야 지 들'''
    rest = re.sub('|'.join(re.escape(x) for x in sorted(set(words.split()), key=len, reverse=True)), '', q)
    if rest:return None
    return {'entity':'project','operation':'change_rank','basis':'change_events',
            'direction':'newest','limit':None,'period':None,'per_project':False}


def answer(w, c, projects, intent):
    empty = {'kind':'metadata','mode':'project_owner' if intent['operation']=='owner' else 'change_rank',
             'answerable':True,'points':[],'sources':[],'result_project_ids':[]}
    if not projects:
        return {**empty,'message':'조회 가능한 등록 프로젝트가 없습니다.'}
    if intent['operation']=='owner':
        if len(projects)>1 and not intent['per_project']:
            return {'kind':'clarification','answerable':False,'points':[],'sources':[],
                    'projects':[{'id':p['id'],'name':p['name']} for p in projects],
                    'message':'어느 프로젝트의 PM을 확인할까요? 프로젝트를 선택해 주세요.'}
        people={p['id']:p['name'] for p in w.all_records(c,'person')}
        return {**empty,'message':'','result_project_ids':[p['id'] for p in projects],
                'points':[{'project_id':p['id'],'project_name':p['name'],
                    'text':'등록된 프로젝트 PM은 '+people[p['pm']]+'입니다.' if p.get('pm') in people else '등록된 프로젝트 PM 정보를 확인할 수 없습니다.',
                    'sources':[]} for p in projects],
                'notice':'프로젝트에 등록된 PM 기준입니다. 개별 업무 담당자는 업무별로 확인합니다.'}
    ids={p['id'] for p in projects}
    counts=dict.fromkeys(ids,0)
    events,_=active_changes(w,c,projects)
    for event in events:counts[event['project_id']]+=1
    most=max(counts.values(),default=0)
    notice='변경이력에 표시되는 기록 수 기준입니다. 최초 합의·요청·합의·보류·철회를 포함하며, 제외·삭제·구버전 기록은 세지 않습니다.'
    if not most:
        return {**empty,'message':'조회 가능한 프로젝트에 변경 기록이 없습니다.','notice':notice,'count':0}
    winners=sorted((p for p in projects if counts[p['id']]==most),key=lambda p:(p['name'],p['id']))
    return {**empty,'message':'변경 기록이 가장 많은 프로젝트입니다.' if len(winners)==1 else f'변경 기록 {most}건으로 공동 1위인 프로젝트 {len(winners)}개입니다.',
            'points':[{'project_id':p['id'],'project_name':p['name'],'text':f'변경 기록 {most}건','sources':[]} for p in winners],
            'result_project_ids':[p['id'] for p in winners],'count':most,
            'compared_projects':len(projects),'notice':notice}
