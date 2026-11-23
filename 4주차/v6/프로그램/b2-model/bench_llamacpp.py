"""llama.cpp 속도 측정. 앱 코드는 건드리지 않는다.
먼저 다른 창에서 llama-server 를 띄운 뒤 실행한다 (기본 주소 http://127.0.0.1:8080)."""
import json,sqlite3,sys,time,urllib.request
from pathlib import Path
try:sys.stdout.reconfigure(encoding='utf-8')
except Exception:pass
URL=(sys.argv[1] if len(sys.argv)>1 else 'http://127.0.0.1:8080').rstrip('/')
DB=Path(__file__).resolve().parent.parent/'b2-service'/'data'/'v17'/'workspace.sqlite3'
BASELINE=15.8  # 현재 엔진(bitsandbytes 4bit) 실측: 2,246토큰 / 142초

def meeting_text():
    rows=[json.loads(r[0]) for r in sqlite3.connect(DB).execute("select payload from records where kind='import'")]
    rows=[r for r in rows if r.get('source')]
    if not rows:raise SystemExit('측정에 쓸 회의록이 없습니다. 앱에서 회의록을 한 건 올린 뒤 다시 실행해 주세요.')
    row=max(rows,key=lambda r:len(r['source']))
    return row.get('title') or '',row.get('edited_body') or row['source']

def ask(messages,max_tokens):
    body=json.dumps({'messages':messages,'max_tokens':max_tokens,'temperature':0,'stream':False}).encode()
    req=urllib.request.Request(URL+'/v1/chat/completions',data=body,headers={'Content-Type':'application/json'})
    started=time.perf_counter()
    with urllib.request.urlopen(req,timeout=900) as res:out=json.loads(res.read())
    return out,time.perf_counter()-started

title,text=meeting_text()
system=('제조 장비 회의록에서 실행 업무와 추가 확인 사항을 JSON으로 추출한다. '
        '출력 형식: {"items":[{"title":"","description":"","kind":"업무","owner":"","due":null,"evidence":""}],'
        '"summary":[{"text":""}],"decisions":[{"text":""}],"overall":""}. '
        'items는 최대 6개, description은 1~3줄, summary와 decisions는 각각 3~5개. 원문에 있는 사실만 쓴다. JSON만 출력한다.')
messages=[{'role':'system','content':system},{'role':'user','content':text}]
print(f'회의록: {title} ({len(text):,}자)\n주소: {URL}\n')
try:ask([{'role':'user','content':'준비'}],8)
except Exception as exc:raise SystemExit(f'llama-server 에 연결하지 못했습니다: {exc}\n다른 창에서 llama-server 가 켜져 있는지 확인해 주세요.')
results=[]
for n in (1,2):
    out,seconds=ask(messages,2300)
    usage=out.get('usage') or {};timings=out.get('timings') or {}
    made=usage.get('completion_tokens') or 0
    speed=timings.get('predicted_per_second') or (made/seconds if seconds else 0)
    results.append(speed)
    print(f'[{n}회차] 입력 {usage.get("prompt_tokens","?")}토큰 · 출력 {made}토큰 · 전체 {seconds:.1f}초')
    if timings:print(f'        입력 읽기 {timings.get("prompt_ms",0)/1000:.1f}초 · 생성 {timings.get("predicted_ms",0)/1000:.1f}초 · 생성 속도 {speed:.1f}토큰/초')
    else:print(f'        생성 속도(전체 시간 기준) {speed:.1f}토큰/초')
best=max(results)
print(f'\n현재 엔진 {BASELINE}토큰/초 → llama.cpp {best:.1f}토큰/초 ({best/BASELINE:.1f}배)')
print(f'같은 분량(2,246토큰) 생성 예상: 142초 → {2246/best:.0f}초' if best else '')
(Path(__file__).resolve().parent/'results'/'bench_llamacpp.json').write_text(json.dumps({'url':URL,'speeds':results,'baseline':BASELINE},ensure_ascii=False),encoding='utf-8')
