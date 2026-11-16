"""Keyword search over registered minutes: matching, ranking, permissions and the evidence export."""
import io, os, tempfile, zipfile
os.environ['B2_TEAM_TESTING']='1'
os.environ['B2_TEAM_DATA_DIR']=tempfile.mkdtemp(prefix='b2-v3-search-')
from fastapi.testclient import TestClient
from work.v3.server import app, legacy as w
from work.v3 import search_engine
import pytest

class Queue:
    def submit(self,*args):pass

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setattr(w,'POOL',Queue())
    monkeypatch.setattr(w,'DATA_DIR',tmp_path);monkeypatch.setattr(w,'DB',tmp_path/'workspace.sqlite3');monkeypatch.setattr(w,'FILES',tmp_path/'files')
    with TestClient(app,headers={'X-B2-Request':'workspace'}) as c:
        assert c.post('/api/demo-login',json={'username':'team1'}).status_code==200
        yield c

def project(c,name,members=('team1','team2')):
    r=c.post('/api/projects',json={'name':name,'members':list(members)});assert r.status_code==201,r.text
    return r.json()

def meeting(c,p,title,date,body):
    content=f'회의명: {title}\n회의일: {date}\n프로젝트: {p["name"]}\n{body}'
    item=c.post('/api/v3/imports',files=[('files',(title+'.txt',content.encode(),'text/plain'))]).json()['items'][0]
    r=c.post('/api/v3/register',json={'items':[{'id':item['id'],'project_id':p['id'],'date':date}]});assert r.status_code==202,r.text
    return r.json()['registered'][0]['id']

def find(c,q,**params):
    r=c.get('/api/v3/search',params={'q':q,**params});assert r.status_code==200,r.text
    return r.json()

def marked(hit):return ''.join(text for text,matched in hit['segments'] if matched)
def sentence(hit):return ''.join(text for text,_ in hit['segments'])

@pytest.fixture
def minutes(client):
    c=client;p=project(c,'한빛셀 코팅라인');other=project(c,'서린 롤프레스')
    ids={
     'first':meeting(c,p,'코팅 폭 사양 협의','2025-02-10','고객사는 코팅 폭을 500 mm 기준으로 요청했다.\n납품일은 2025-12-18로 합의했다.\n배치도는 다음 회의에서 확인한다.'),
     'second':meeting(c,p,'코팅 폭 변경 요청','2025-06-03','고객사가 코팅폭을 520mm로 변경 요청했다.\n변경에 따른 추가 비용은 1,200만원으로 검토한다.\n납기 영향은 보류했다.'),
     'third':meeting(c,p,'변경 합의','2026-01-20','코팅 폭 520mm 변경을 합의했다.\n건조 온도는 1.5도 올리기로 했다.'),
     'other':meeting(c,other,'롤프레스 속도 협의','2025-09-01','라인 속도는 80m/min으로 요청했다.\n코팅 공정과는 무관하다.'),
    }
    return c,p,other,ids

def test_folding_ignores_spacing_case_width_and_separators():
    assert search_engine.fold('코팅 폭')==search_engine.fold('코팅폭')
    assert search_engine.fold('520 MM')==search_engine.fold('５２０mm')
    assert search_engine.fold('1,200만원')=='1200만원'
    assert search_engine.fold('1.5도')=='1.5도' and search_engine.fold('끝났다. 다음')=='끝났다다음'
    assert search_engine.segments('코팅 폭을 520 mm로',['코팅폭','520mm'])==[['코팅 폭',True],['을 ',False],['520 mm',True],['로',False]]

def test_finds_sentences_regardless_of_spacing(minutes):
    c,p,_,ids=minutes
    found=find(c,'코팅폭')
    assert found['mode']=='all' and {x['id'] for x in found['items']}=={ids['first'],ids['second'],ids['third']}
    first=next(x for x in found['items'] if x['id']==ids['first'])
    assert marked(first['hits'][0])=='코팅 폭' and first['hits'][0]['no']>=1 and first['project_name']=='한빛셀 코팅라인'
    assert first['title_segments'][0]==['코팅 폭',True]
    assert {x['id'] for x in find(c,'520 mm')['items']}=={ids['second'],ids['third']}
    assert [x['id'] for x in find(c,'1200만원')['items']]==[ids['second']]
    # A decimal point is kept: 15 must not match 1.5.
    assert find(c,'15도')['total']==0 and find(c,'1.5도')['total']==1

def test_all_words_must_match_and_ranking_prefers_one_sentence(minutes):
    c,_,_,ids=minutes
    found=find(c,'코팅폭 변경 합의')
    assert [x['id'] for x in found['items']][0]==ids['third'] and found['mode']=='all'
    assert any(h['all_terms'] and sentence(h)=='코팅 폭 520mm 변경을 합의했다.' for h in found['items'][0]['hits'])
    assert ids['first'] not in {x['id'] for x in found['items']}
    partial=find(c,'배치도 추가비용')
    assert partial['mode']=='any' and {x['id'] for x in partial['items']}=={ids['first'],ids['second']}
    assert all(x['missing_terms'] for x in partial['items'])

def test_phrase_exclusion_dates_and_order(minutes):
    c,p,_,ids=minutes
    assert [x['id'] for x in find(c,'"변경 요청"')['items']]==[ids['second']]
    without=find(c,'코팅폭 -요청')
    assert all('요청' not in sentence(h) for x in without['items'] for h in x['hits'])
    assert ids['third'] in {x['id'] for x in without['items']}
    assert [x['id'] for x in find(c,'코팅폭',sort='oldest')['items']]==[ids['first'],ids['second'],ids['third']]
    assert [x['id'] for x in find(c,'코팅폭',sort='newest')['items']]==[ids['third'],ids['second'],ids['first']]
    assert [x['id'] for x in find(c,'코팅폭',date_from='2025-03-01',date_to='2025-12-31')['items']]==[ids['second']]
    assert c.get('/api/v3/search',params={'q':'코팅','date_from':'어제'}).status_code==422
    assert c.get('/api/v3/search',params={'q':'코팅','sort':'random'}).status_code==422
    assert find(c,'   ')['total']==0

def test_synonyms_can_be_switched_off(minutes,monkeypatch,tmp_path):
    c,_,_,ids=minutes
    terms=tmp_path/'terms.json';terms.write_text('{"groups":[["납기","납품일"]]}',encoding='utf-8')
    monkeypatch.setattr(search_engine,'TERMS_FILE',terms)
    found=find(c,'납기')
    assert {x['id'] for x in found['items']}=={ids['first'],ids['second']} and found['query']['terms'][0]['also']==['납품일']
    assert [x['id'] for x in find(c,'납기',synonyms='false')['items']]==[ids['second']]

def test_suggests_a_close_spelling_when_nothing_matches(minutes):
    c,_,_,_=minutes
    found=find(c,'배치더')
    assert found['total']==0 and {'for':'배치더','word':'배치도'} in found['suggestions']
    assert find(c,'전혀없는말')['suggestions']==[]

def test_only_readable_projects_are_searched(minutes):
    c,p,other,ids=minutes
    assert ids['other'] in {x['id'] for x in find(c,'코팅')['items']}
    assert [x['id'] for x in find(c,'코팅',project_id=other['id'])['items']]==[ids['other']]
    secret=project(c,'비공개 라인',members=('team1',));hidden=meeting(c,secret,'비공개 협의','2025-10-01','코팅 폭은 비공개로 600mm이다.')
    assert c.delete('/api/v3/meetings/'+ids['third']).status_code==200
    assert ids['third'] not in {x['id'] for x in find(c,'코팅폭')['items']}
    assert c.post('/api/demo-login',json={'username':'team2'}).status_code==200
    seen={x['id'] for x in find(c,'코팅')['items']}
    assert hidden not in seen and ids['first'] in seen
    assert c.get('/api/v3/search',params={'q':'코팅','project_id':secret['id']}).status_code==403
    assert c.get('/api/v3/search/source/'+hidden,params={'q':'코팅'}).status_code==403
    assert c.get('/api/v3/search/export',params={'q':'600mm'}).status_code==404

def test_source_view_marks_the_words(minutes):
    c,_,_,ids=minutes
    r=c.get('/api/v3/search/source/'+ids['second'],params={'q':'코팅폭 보류'});assert r.status_code==200,r.text
    source=r.json()
    assert source['title']=='코팅 폭 변경 요청' and source['has_file']
    # The header line of the document ("회의명: …") is part of the registered text and matches too.
    assert len(source['hit_ids'])==3
    texts=[''.join(t for t,_ in line['segments']) for line in source['lines']]
    assert '납기 영향은 보류했다.' in texts
    assert c.get('/api/v3/search/source/unknown').status_code==404

def test_export_is_a_word_document_of_the_original_sentences(minutes):
    c,_,_,ids=minutes
    r=c.get('/api/v3/search/export',params={'q':'코팅폭 변경','sort':'oldest'});assert r.status_code==200,r.text
    assert 'wordprocessingml' in r.headers['content-type'] and "filename*=UTF-8''" in r.headers['content-disposition']
    xml=zipfile.ZipFile(io.BytesIO(r.content)).read('word/document.xml').decode('utf-8')
    import re
    text=re.sub(r'<[^>]+>','',xml)
    assert '회의록 검색 근거 자료' in text and '고객사가 코팅폭을 520mm로 변경 요청했다.' in text and '김양일' in text
    assert text.index('코팅 폭 변경 요청')<text.index('변경 합의') and '원문에서 그대로' in text
    assert c.get('/api/v3/search/export',params={'q':'없는단어입니다'}).status_code==404

def test_many_minutes_stay_fast(client):
    import time
    c=client;p=project(c,'대량 검증')
    body='\n'.join(f'{i}번 항목은 일반 논의로 기록한다. 설비 사양과 일정은 이전과 같다.' for i in range(120))
    with w.connect() as db:
        for n in range(400):
            text=body+(f'\n특수 키워드 알파{n}은 합의했다.' if n%50==0 else '')
            w.save(db,'meeting',{'id':f'bulk-{n}','project_id':p['id'],'title':f'정기 회의 {n}','date':f'2025-{n%12+1:02d}-{n%28+1:02d}','source':text,
                'lines':[{'id':'L'+str(i+1).zfill(3),'text':t} for i,t in enumerate(text.splitlines())],'author':'team1','candidates':[],'analysis_state':'ready','version':1,'revision':1,'revisions':[]})
    started=time.perf_counter();first=find(c,'특수키워드 합의');cold=time.perf_counter()-started
    started=time.perf_counter();again=find(c,'알파50');warm=time.perf_counter()-started
    assert first['total']==8 and first['searched']==400 and [x['id'] for x in again['items']]==['bulk-50']
    assert cold<6 and warm<3,(cold,warm)
