"""Connected B2 interface; reuses existing local storage, identity and models."""
from pathlib import Path
from contextlib import asynccontextmanager
import os
from fastapi.responses import FileResponse
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

@app.get('/')
def index():
    return FileResponse(Path(__file__).with_name('workspace.html'), media_type='text/html')

@app.get('/previous')
def previous():
    return FileResponse(legacy.ROOT/'work'/'v17'/'workspace.html', media_type='text/html')
