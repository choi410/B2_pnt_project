"""Conversational presentation of verified results, without another model call."""
def present(result):
    mode=result.get('mode')
    if mode=='project_list' and result.get('answerable'):
        total=result.get('total_count',result.get('count',0)); shown=len(result.get('projects',[]))
        if ' 님이 PM을 ' in result.get('message',''):return result
        result['message']=f'등록된 프로젝트는 총 {total}개예요.' if shown==total else f'등록된 프로젝트 총 {total}개 중 {shown}개를 보여드릴게요.'
    elif mode=='project_owner':
        for p in result.get('points',[]):
            if p.get('text','').startswith('등록된 프로젝트 PM은 '):
                p['text']=p['text'].replace('등록된 프로젝트 PM은 ','PM은 ',1)
    elif mode=='meeting_lookup' and result.get('answerable') and '표시했습니다' in result.get('message',''):
        result['message']=f'조건에 맞는 회의록 {result.get("count",0)}건을 찾았어요.'
    return result
