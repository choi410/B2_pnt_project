"""Connected B2 interface; reuses existing local storage, identity and models."""
from pathlib import Path
from contextlib import asynccontextmanager
import os
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from work.v17 import storage
from work.v17 import server as legacy
from work.v3.service import build_router,register_revision
from work.v3 import question_policy
from work.v17.questions import build_router as questions_router
from work.v3.trash import build_router as trash_router

app = legacy.app
def retain_routes(router):
    # FastAPI can retain included routers instead of flattening their routes.
    for route in router.routes:
        child=getattr(route,'original_router',None)
        if child is not None:retain_routes(child)
    router.routes[:] = [r for r in router.routes if getattr(r,'path','')!='/' and not getattr(r,'path','').startswith('/api/questions')]
retain_routes(app.router)
app.include_router(questions_router(legacy,question_policy))
app.include_router(build_router(legacy))
app.include_router(trash_router(legacy))
original_lifespan=app.router.lifespan_context
@asynccontextmanager
async def lifespan(app):
    async with original_lifespan(app):
        with legacy.connect() as c:
            for m in legacy.all_records(c,'meeting'):
                if m.get('v3_job') and not m.get('deleted_at') and (m.get('registered_revision')!=m['revision'] or not any(r['number']==m['revision'] for r in m.get('revisions',[]))):
                    register_revision(m);legacy.save(c,'meeting',m)
        yield
app.router.lifespan_context=lifespan

HERE=Path(__file__).parent
# The built screen predates Supabase sign-in. This runs before it and sends the browser to
# the sign-in page on sign-out or when the session ends, and links to the management page.
SESSION_GUARD="""<style>.admin-entry{position:fixed;left:16px;bottom:16px;z-index:40;padding:7px 12px;border:1px solid var(--line);border-radius:7px;background:var(--chrome);color:var(--blue);font-size:.8667rem;text-decoration:none}.admin-entry:hover{border-color:var(--blue)}</style><script>(function(){var send=window.fetch;window.fetch=function(input){return send.apply(this,arguments).then(function(res){try{var path=new URL(typeof input==='string'?input:input.url,location.href).pathname;if(path==='/api/logout'||(res.status===401&&path.indexOf('/api/')===0))location.replace('/login')}catch(e){}return res})};send('/api/me',{credentials:'same-origin'}).then(function(r){return r.ok?r.json():null}).then(function(me){if(!me||!(me.can_manage_users||me.can_manage_projects))return;var a=document.createElement('a');a.className='admin-entry';a.href='/admin';a.textContent=me.can_manage_users?'사용자·권한 관리':'프로젝트 참여자 관리';document.body.appendChild(a)}).catch(function(){})})();</script>"""
# The built screen filters only titles and AI notes. This link opens the search over the
# registered text of the minutes (search.html), which needs no rebuild of that screen.
SEARCH_ENTRY="""<style>.search-entry{position:fixed;left:16px;bottom:16px;z-index:40;padding:7px 12px;border:1px solid var(--line);border-radius:7px;background:var(--chrome);color:var(--blue);font-size:.8667rem;text-decoration:none}.search-entry:hover{border-color:var(--blue)}.admin-entry{bottom:58px}</style><a class="search-entry" href="/search">회의록 본문 검색</a>"""
_workspace={}
def workspace_page():
    path=HERE/'workspace.html';stamp=path.stat().st_mtime_ns
    if _workspace.get('stamp')!=stamp:
        extra=(SESSION_GUARD if storage.SHARED else '')+SEARCH_ENTRY
        _workspace.update(stamp=stamp,html=path.read_text(encoding='utf-8').replace('<body>','<body>'+extra,1))
    return _workspace['html']

@app.get('/')
def index(req:Request):
    if storage.SHARED and not legacy.session_user(req):return RedirectResponse('/login',303)
    return HTMLResponse(workspace_page())

@app.get('/search')
def search_page(req:Request):
    if storage.SHARED and not legacy.session_user(req):return RedirectResponse('/login',303)
    return FileResponse(HERE/'search.html', media_type='text/html')

@app.get('/login')
def login_page(req:Request):
    if not storage.SHARED or legacy.session_user(req):return RedirectResponse('/',303)
    return FileResponse(HERE/'login.html', media_type='text/html')

@app.get('/admin')
def admin_page(req:Request):
    if not storage.SHARED:return RedirectResponse('/',303)
    if not legacy.session_user(req):return RedirectResponse('/login',303)
    return FileResponse(HERE/'admin.html', media_type='text/html')

@app.get('/previous')
def previous():
    return FileResponse(legacy.ROOT/'work'/'v17'/'workspace.html', media_type='text/html')
