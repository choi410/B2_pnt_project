"""Customer approval by mail: a single-use link, recorded as 'approval_request' records.

The result is a display state only; it never changes the change history.
Only the token hash is stored. The body sent to the customer is kept with the request,
so a later source edit does not change what the customer was shown.
"""
from datetime import datetime, timedelta
from html import escape
import hashlib, io, json, re, secrets
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from work.v17 import team_config
from work.v3 import mailer
from work.v3.management import record, require_lead
from work.v17.intake_review import PDF_LOCK, preview_pages

KIND='approval_request'
EMAIL=re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
SHOWN=('sent','approved','rejected')   # states whose link still shows the meeting body
CLOSED='더 이상 사용할 수 없는 링크입니다. 새로 받은 메일의 링크를 사용해 주세요.'


class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class SendRequest(Strict):
    email:str=Field(min_length=3,max_length=200)
    name:str=Field(default='',max_length=50)
    message:str=Field(default='',max_length=1000)
class Decision(Strict):
    decision:str
    comment:str=Field(default='',max_length=1000)


def token_hash(token):
    return hashlib.sha256((token or '').encode()).hexdigest()


def expire_days():
    try:return max(1,int(mailer.setting('APPROVAL_EXPIRE_DAYS','7')))
    except ValueError:return 7


def link_base(origin=''):
    """Address the mail link starts with; it must be one this server actually answers on.

    APP_BASE_URL is used only when it is such an address. Otherwise the address the PM is
    using right now is taken, so a value copied from another project cannot break the link.
    """
    for base in (mailer.setting('APP_BASE_URL').rstrip('/'),origin.rstrip('/')):
        if base in team_config.ORIGINS:return base
    return f'http://127.0.0.1:{team_config.PORT}'


def link_for(token,origin=''):
    return link_base(origin)+'/#/approval/'+token


def effective_status(request,now):
    """An unanswered request past its deadline is shown as expired."""
    if request['status']=='sent' and datetime.fromisoformat(request['expires_at'])<datetime.fromisoformat(now):return 'expired'
    return request['status']


def summary(request,now,revision=None):
    """Fields the workspace shows next to a meeting."""
    items=request.get('items') or []
    return {'id':request['id'],'status':effective_status(request,now),'email':request['email'],'sent_at':request['sent_at'],'responded_at':request.get('responded_at'),'comment':request.get('comment'),'revision':request['revision'],'outdated':revision is not None and request['revision']!=revision,'item_ids':[x['id'] for x in items],'items':items,'applied_at':request.get('applied_at')}


def meeting_items(w,c,m):
    """요구·변경 항목 중 이 회의록 현재 본문에 속한 것. (검수 대기, 확인된 것)"""
    rows=[e for e in w.all_records(c,'change_event') if e['meeting_id']==m['id'] and not e.get('superseded_by_revision') and e.get('source_revision')==m['revision'] and e.get('review_state')!='제외']
    waiting=[e for e in rows if e.get('review_state')!='확인됨']
    done=sorted((e for e in rows if e.get('review_state')=='확인됨'),key=lambda e:(e.get('category') or '',e.get('title') or ''))
    return waiting,[{'id':e['id'],'title':e.get('title',''),'category':e.get('category',''),'before':e.get('before') or '','after':e.get('after') or '','state':'합의' if e.get('business_state')=='확정' else e.get('business_state','')} for e in done]


def item_line(x):
    return f"{x['title']}: "+(f"{x['before']} → " if x['before'] else '')+x['after']+(f" ({x['state']})" if x['state'] and x['state']!='합의' else '')


def latest_by_meeting(requests):
    latest={}
    for request in sorted(requests,key=lambda x:(x['sent_at'],x.get('sequence',0))):latest[request['meeting_id']]=request
    return latest


def mail_body(project_name,meeting,sender,name,message,link,expires_at,items=()):
    subject=f"[회의록 합의 요청] {project_name} - {meeting['title']}"
    greeting=f'{name}님, 안녕하세요.' if name else '안녕하세요.'
    title=meeting['title']+(f" ({meeting['date']})" if meeting.get('date') else '')
    deadline=expires_at[:16].replace('T',' ')
    lines=[greeting,'',f'{sender} 님이 아래 회의록의 확인과 합의를 요청했습니다.','',f'프로젝트: {project_name}',f'회의록: {title}']
    if message:lines+=['','전달 메시지:',message]
    if items:lines+=['',f'합의 요청 항목 ({len(items)}건):']+['- '+item_line(x) for x in items]
    lines+=['','아래 주소에서 회의록 내용을 확인한 뒤 합의 또는 반려를 선택해 주세요.',link,'',f'이 링크는 {deadline}까지 한 번만 사용할 수 있습니다.']
    note=f'<p style="white-space:pre-wrap;background:#f4f6f8;padding:10px 12px;border-radius:6px">{escape(message)}</p>' if message else ''
    if items:note+=f'<p style="margin:18px 0 6px;font-weight:bold">합의 요청 항목 {len(items)}건</p><ul style="margin:0;padding-left:20px">'+''.join(f'<li style="margin:3px 0">{escape(item_line(x))}</li>' for x in items)+'</ul>'
    html=f"""<div style="font-family:'Malgun Gothic',sans-serif;font-size:14px;color:#1c2733;line-height:1.7;max-width:560px">
<p>{escape(greeting)}</p>
<p><b>{escape(sender)}</b> 님이 아래 회의록의 확인과 합의를 요청했습니다.</p>
<table style="border-collapse:collapse;font-size:14px">
<tr><td style="padding:2px 12px 2px 0;color:#5b6875">프로젝트</td><td>{escape(project_name)}</td></tr>
<tr><td style="padding:2px 12px 2px 0;color:#5b6875">회의록</td><td>{escape(title)}</td></tr>
</table>
{note}
<p style="margin:22px 0"><a href="{escape(link)}" style="background:#1f3a5f;color:#fff;text-decoration:none;padding:10px 20px;border-radius:6px;display:inline-block">회의록 확인하고 합의하기</a></p>
<p style="color:#5b6875;font-size:13px">버튼이 열리지 않으면 이 주소를 브라우저에 붙여넣어 주세요.<br>{escape(link)}</p>
<p style="color:#5b6875;font-size:13px">이 링크는 {escape(deadline)}까지 한 번만 사용할 수 있습니다.</p>
</div>"""
    return subject,'\n'.join(lines),html


def build_router(w):
    r=APIRouter(prefix='/api/v3')
    def of_meeting(c,mid):
        rows=c.execute("SELECT payload FROM records WHERE kind=? AND json_extract(payload,'$.meeting_id')=?",(KIND,mid))
        return sorted((json.loads(row[0]) for row in rows),key=lambda x:(x['sent_at'],x.get('sequence',0)),reverse=True)
    def original_pdf(request,m):
        # The uploaded file's page images, shown when the mail went out before any web edit,
        # so the reader sees the meeting minutes in their original layout.
        path=m.get('pdf') if request.get('original') else None
        return path if path and Path(path).is_file() else None
    def by_token(c,token):
        row=c.execute("SELECT payload FROM records WHERE kind=? AND json_extract(payload,'$.token_hash')=?",(KIND,token_hash(token))).fetchone()
        if not row:raise HTTPException(404,'유효하지 않은 링크입니다. 회의록이 삭제되었거나 주소가 잘못되었습니다.')
        request=json.loads(row[0])
        # A meeting or project in the trash hides the request until it is restored.
        m=w.read(c,'meeting',request['meeting_id']);p=w.read(c,'project',m['project_id'])
        if m.get('deleted_at') or p.get('deleted_at'):raise HTTPException(410,'지금은 사용할 수 없는 링크입니다. 담당자에게 문의해 주세요.')
        return request,p,m
    @r.post('/meetings/{mid}/approval-requests',status_code=201)
    def send(mid,body:SendRequest,req:Request,actor=Depends(w.user)):
        email=body.email.strip();name=body.name.strip();message=body.message.strip()
        if not EMAIL.match(email):raise HTTPException(422,'받는 사람 이메일 주소를 확인해 주세요.')
        with w.connect() as c:
            m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor,True)
            if m.get('deleted_at'):raise HTTPException(409,'휴지통에 있는 회의록입니다. 복원한 뒤 보내 주세요.')
            if m.get('analysis_state') in ('queued','running') or m.get('analysis_stale'):raise HTTPException(409,'회의록 분석이 끝나고 검수를 마친 뒤 보내 주세요.')
            waiting,items=meeting_items(w,c,m)
            if waiting:raise HTTPException(409,f'검수가 끝나지 않은 항목이 {len(waiting)}건 있습니다. 검수를 마쳐 회의록을 등록한 뒤 보내 주세요.')
        token=secrets.token_urlsafe(32);link=link_for(token,f"{req.url.scheme}://{req.headers.get('host','')}")
        expires_at=(datetime.fromisoformat(w.now())+timedelta(days=expire_days())).isoformat(timespec='seconds')
        # Send before writing, outside any transaction: a slow or failed send changes nothing.
        try:mailer.send(email,*mail_body(p['name'],m,actor['name'],name,message,link,expires_at,items))
        except mailer.MailError as exc:raise HTTPException(502,str(exc))
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            previous=of_meeting(c,mid)
            for old in previous:
                # A new request replaces the link of any request still waiting.
                if old['status']=='sent':old['status']='canceled';w.save(c,KIND,old)
            request={'id':w.uid(),'meeting_id':mid,'project_id':m['project_id'],'token_hash':token_hash(token),'email':email,'name':name,'message':message,'status':'sent','comment':'','requested_by':actor['id'],'sent_at':w.now(),'expires_at':expires_at,'responded_at':None,'sequence':len(previous)+1,'revision':m['revision'],'title':m['title'],'date':m.get('date',''),'lines':[x['text'] for x in m.get('lines',[])],'original':m['revision']==1,'items':items}
            request['delivery_mode']=mailer.mode()
            w.save(c,KIND,request)
        result={'id':request['id'],'status':'sent','email':email,'expires_at':expires_at,'mode':mailer.mode()}
        if mailer.mode()!='smtp':result['link']=link   # nothing was mailed; let the PM open it
        return result
    @r.get('/meetings/{mid}/approval-requests')
    def history(mid,actor=Depends(w.user)):
        with w.connect() as c:
            m=w.read(c,'meeting',mid);w.project(c,m['project_id'],actor);now=w.now()
            return [{k:x.get(k) for k in ('id','email','name','message','comment','sent_at','expires_at','responded_at','requested_by','revision','applied_at')}|{'status':effective_status(x,now),'item_count':len(x.get('items') or [])} for x in of_meeting(c,mid)]
    @r.post('/meetings/{mid}/approval-apply')
    def apply(mid,actor=Depends(w.user)):
        """상대가 합의한 항목 중 아직 요청·보류인 것을 PM이 합의로 바꾼다. 회신만으로는 바꾸지 않는다."""
        with w.connect() as c:
            c.execute('BEGIN IMMEDIATE');m=w.read(c,'meeting',mid);p=w.project(c,m['project_id'],actor)
            require_lead(p,actor)
            if m.get('deleted_at'):raise HTTPException(409,'휴지통에 있는 회의록입니다.')
            latest=next(iter(of_meeting(c,mid)),None)
            if not latest or effective_status(latest,w.now())!='approved':raise HTTPException(409,'합의된 요청이 없습니다.')
            waiting,current=meeting_items(w,c,m)
            if waiting or latest['revision']!=m['revision'] or latest.get('items',[])!=current:
                raise HTTPException(409,'합의 이후 회의록 또는 변경 항목이 바뀌었습니다. 다시 합의를 요청해 주세요.')
            done=[]
            for x in latest.get('items') or []:
                try:e=w.read(c,'change_event',x['id'])
                except HTTPException:continue
                if e.get('superseded_by_revision') or e.get('review_state')!='확인됨' or e.get('business_state') not in ('요청','보류'):continue
                e['edit_history']=[*e.get('edit_history',[]),{'at':w.now(),'by':actor['id'],'action':'합의 반영','record':{k:v for k,v in e.items() if k!='edit_history'}}]
                e.update(business_state='확정',customer_agreed_at=latest.get('responded_at'),version=e['version']+1,updated_at=w.now(),updated_by=actor['id']);w.save(c,'change_event',e);done.append(e['id'])
            if done:
                latest.update(applied_at=w.now(),applied_by=actor['id']);w.save(c,KIND,latest)
        return {'applied':len(done),'ids':done}
    # The two routes below are opened from the mail link without a login; the token is the key.
    @r.get('/approvals/{token}')
    def view(token):
        with w.connect() as c:
            request,p,m=by_token(c,token);status=effective_status(request,w.now())
            requester=next((x['name'] for x in w.all_records(c,'person') if x['id']==request['requested_by']),'')
        result={k:request.get(k) for k in ('title','date','name','sent_at','expires_at','responded_at','comment')}|{'items':request.get('items') or []}|{'status':status,'project_name':p['name'],'requested_by_name':requester}
        # A replaced or expired link does not show the meeting body.
        if status in SHOWN:result.update(message=request['message'],lines=request['lines'],pages=preview_pages(original_pdf(request,m)))
        return result
    @r.get('/approvals/{token}/pages/{page}')
    def page(token,page:int):
        with w.connect() as c:
            request,_,m=by_token(c,token)
            if effective_status(request,w.now()) not in SHOWN:raise HTTPException(410,CLOSED)
            path=original_pdf(request,m)
        if not path:raise HTTPException(404,'원본 미리보기가 없습니다.')
        import pypdfium2 as pdfium
        with PDF_LOCK:
            with pdfium.PdfDocument(path) as doc:
                if page<1 or page>len(doc):raise HTTPException(404,'페이지를 찾을 수 없습니다.')
                sheet=doc[page-1]
                try:
                    bitmap=sheet.render(scale=min(1.8,2200/max(sheet.get_size())))
                    try:
                        picture=bitmap.to_pil();buffer=io.BytesIO();picture.save(buffer,format='PNG');picture.close()
                    finally:bitmap.close()
                finally:sheet.close()
        return Response(buffer.getvalue(),media_type='image/png')
    @r.post('/approvals/{token}')
    def respond(token,body:Decision):
        if body.decision not in ('approved','rejected'):raise HTTPException(422,'승인 또는 반려를 선택해 주세요.')
        with w.connect() as c:
            # The write lock makes two simultaneous clicks resolve to one answer.
            c.execute('BEGIN IMMEDIATE');request,p,m=by_token(c,token);status=effective_status(request,w.now())
            if status in ('approved','rejected'):raise HTTPException(409,'이미 처리된 요청입니다.')
            if status=='expired':raise HTTPException(410,'링크의 유효 기간이 지났습니다. 담당자에게 다시 요청해 주세요.')
            if status!='sent':raise HTTPException(410,CLOSED)
            request.update(status=body.decision,comment=body.comment.strip(),responded_at=w.now());w.save(c,KIND,request)
            leaders=[u['id'] for u in w.all_records(c,'person') if u['id'] in p['members'] and u.get('level')=='leader']
            record(w,c,p,'고객 합의 회신' if body.decision=='approved' else '고객 반려 회신','external',
                   mid=m['id'],title=m['title'],reason=body.comment.strip(),kind='mail',
                   recipients=set(leaders+[request['requested_by']]),event_id=f"mail:{request['id']}:reply")
        return {'status':body.decision}
    return r
