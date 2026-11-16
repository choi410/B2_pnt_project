"""Keyword search over the registered text of meeting minutes.

The minutes are evidence, so a result is always a sentence that literally stands in a
registered document: no summaries, no generated text. Matching ignores spacing, letter
case, full/half width forms and thousands separators, which is what makes Korean compound
words and unit notations ("코팅 폭" / "코팅폭", "520 mm" / "520mm") findable.
"""
import json, math, re, unicodedata
from difflib import SequenceMatcher
from pathlib import Path

TERMS_FILE=Path(__file__).with_name('search_terms.json')
MAX_TERMS=8
DROP=set('·_()-‐‑–—[]{}<>「」『』“”‘’"\'')
_folded={}
_groups={'stamp':None,'groups':[]}


def fold_map(text):
    """Folded text and, for each folded character, its position in the original."""
    out=[];where=[];text=text or '';size=len(text)
    for i,ch in enumerate(text):
        if ch.isspace() or ch in DROP:continue
        if ch in '.,' :
            between=i>0 and i+1<size and text[i-1].isdigit() and text[i+1].isdigit()
            # "1,000" reads as 1000 and "1.5" keeps its point; other dots and commas separate words.
            if ch==',' or not between:continue
        for piece in unicodedata.normalize('NFKC',ch).casefold():
            if piece.isspace() or piece in DROP:continue
            out.append(piece);where.append(i)
    return ''.join(out),where


def fold(text):return fold_map(text)[0]


def synonym_groups():
    """Words the workspace treats as the same thing (search_terms.json, editable)."""
    try:stamp=TERMS_FILE.stat().st_mtime_ns
    except OSError:return []
    if _groups['stamp']!=stamp:
        try:raw=json.loads(TERMS_FILE.read_text(encoding='utf-8-sig')).get('groups',[])
        except (OSError,ValueError,AttributeError):raw=[]
        groups=[]
        for group in raw:
            if isinstance(group,list):
                words=[(str(x).strip(),fold(str(x))) for x in group if str(x).strip()]
                words=[w for w in words if w[1]]
                if len(words)>1:groups.append(words)
        _groups.update(stamp=stamp,groups=groups)
    return _groups['groups']


def parse(query,synonyms=True):
    """Space separated words must all appear; "quoted words" stay together; -word removes sentences."""
    include=[];exclude=[]
    for quoted,minus,word in re.findall(r'(-?"[^"]+")|(-\S+)|(\S+)',query or ''):
        text=quoted or minus or word;negative=text.startswith('-')
        text=text.lstrip('-').strip('"').strip();key=fold(text)
        if not key:continue
        if negative:
            if key not in exclude:exclude.append(key)
            continue
        if any(t['key']==key for t in include) or len(include)>=MAX_TERMS:continue
        variants=[key];also=[]
        if synonyms:
            for group in synonym_groups():
                if any(k==key for _,k in group):
                    for label,k in group:
                        if k not in variants:variants.append(k);also.append(label)
        include.append({'text':text,'key':key,'variants':variants,'also':also})
    return include,exclude


def folded_lines(m):
    stamp=(m.get('version'),m.get('revision'),len(m.get('lines') or []))
    held=_folded.get(m['id'])
    if not held or held[0]!=stamp:
        held=(stamp,[fold(x.get('text','')) for x in m.get('lines') or []])
        if len(_folded)>4000:_folded.clear()
        _folded[m['id']]=held
    return held[1]


def segments(text,variants):
    """The text cut into [piece, matched] pairs so the screen can mark the matched words."""
    folded,where=fold_map(text);spans=[]
    for v in variants:
        start=folded.find(v)
        while start>=0:
            spans.append((where[start],where[start+len(v)-1]+1));start=folded.find(v,start+1)
    if not spans:return [[text,False]] if text else []
    spans.sort();merged=[list(spans[0])]
    for a,b in spans[1:]:
        if a<=merged[-1][1]:merged[-1][1]=max(merged[-1][1],b)
        else:merged.append([a,b])
    out=[];at=0
    for a,b in merged:
        if a>at:out.append([text[at:a],False])
        out.append([text[a:b],True]);at=b
    if at<len(text):out.append([text[at:],False])
    return out


def jamo(text):
    out=[]
    for ch in text:
        code=ord(ch)-0xAC00
        if 0<=code<11172:out.extend((chr(0x1100+code//588),chr(0x1161+(code%588)//28),chr(0x11A7+code%28)))
        else:out.append(ch)
    return ''.join(out)


def suggest(term,meetings,limit=3):
    """Close spellings that do occur, for a word that was found nowhere."""
    if len(term)<2:return []
    target=jamo(term);counts={}
    for m in meetings:
        for line in m.get('lines') or []:
            for token in re.findall(r'[0-9A-Za-z가-힣]+',line.get('text','')):
                token=token.casefold()
                for size in (len(term),len(term)+1,len(term)-1):
                    if 2<=size<=len(token):counts[token[:size]]=counts.get(token[:size],0)+1
    scored=[]
    for word,count in counts.items():
        if word==term or abs(len(word)-len(term))>1:continue
        ratio=SequenceMatcher(None,target,jamo(word)).ratio()
        if ratio>=0.8:scored.append((ratio,count,word))
    scored.sort(reverse=True);out=[]
    for _,_,word in scored:
        # Prefer the shortest form: "코팅폭" rather than "코팅폭을".
        if not any(word.startswith(x) or x.startswith(word) for x in out):out.append(word)
        if len(out)==limit:break
    return out


def search(meetings,projects,query,sort='relevance',date_from='',date_to='',synonyms=True,per_meeting=30,limit=50):
    """meetings: visible, undeleted meeting records. projects: {id: project}."""
    include,exclude=parse(query,synonyms)
    described={'terms':[{'text':t['text'],'also':t['also']} for t in include],'excluded':exclude}
    if not include:return {'query':described,'mode':'all','total':0,'hits_total':0,'items':[],'suggestions':[],'searched':0}
    pool=[m for m in meetings if (not date_from or (m.get('date') or '')>=date_from) and (not date_to or (m.get('date') or '9999')<=date_to)]
    found=[];frequency=[0]*len(include)
    for m in pool:
        lines=folded_lines(m);title=fold(m.get('title',''))
        per_term=[];rows={}
        for index,t in enumerate(include):
            in_title=any(v in title for v in t['variants']);count=0
            for number,text in enumerate(lines):
                if any(x in text for x in exclude):continue
                if any(v in text for v in t['variants']):
                    count+=1;rows.setdefault(number,set()).add(index)
            per_term.append((count,in_title))
            if count or in_title:frequency[index]+=1
        matched=sum(1 for count,in_title in per_term if count or in_title)
        if matched:found.append((m,per_term,rows,matched))
    complete=[x for x in found if x[3]==len(include)]
    mode='all' if complete or len(include)==1 else 'any'
    chosen=complete if mode=='all' else found
    total_docs=max(len(pool),1);items=[]
    variants=[v for t in include for v in t['variants']]
    for m,per_term,rows,matched in chosen:
        score=0.0
        for index,(count,in_title) in enumerate(per_term):
            if not (count or in_title):continue
            rarity=math.log(1+total_docs/(1+frequency[index]))
            score+=rarity*(1+math.log(1+count))+(1.5 if in_title else 0)
        together=max((len(v) for v in rows.values()),default=0)
        # Sentences that hold every word are the strongest evidence.
        if len(include)>1 and together==len(include):score+=3+sum(1 for v in rows.values() if len(v)==len(include))*0.2
        score+=matched*2
        order=sorted(rows,key=lambda n:(-len(rows[n]),n))[:per_meeting]
        source=m.get('lines') or [];hits=[]
        for number in sorted(order):
            line=source[number]
            hits.append({'id':line.get('id'),'no':number+1,'segments':segments(line.get('text',''),variants),'all_terms':len(rows[number])==len(include),
                'before':source[number-1].get('text','') if number else '','after':source[number+1].get('text','') if number+1<len(source) else ''})
        project=projects.get(m['project_id'],{})
        items.append({'id':m['id'],'title':m.get('title',''),'title_segments':segments(m.get('title',''),variants),'date':m.get('date',''),
            'project_id':m['project_id'],'project_name':project.get('name',''),'score':round(score,3),'hit_count':len(rows),'hits':hits,
            'matched_terms':[include[i]['text'] for i,(count,in_title) in enumerate(per_term) if count or in_title],
            'missing_terms':[include[i]['text'] for i,(count,in_title) in enumerate(per_term) if not (count or in_title)],
            'excerpts':[{'id':source[n].get('id'),'text':source[n].get('text','')} for n in sorted(order)[:3]]})
    if sort=='newest':items.sort(key=lambda x:(x['date'] or '',x['score']),reverse=True)
    elif sort=='oldest':items.sort(key=lambda x:(x['date'] or '9999',-x['score']))
    else:items.sort(key=lambda x:(x['score'],x['date'] or ''),reverse=True)
    suggestions=[]
    for index,t in enumerate(include):
        if not frequency[index]:
            for word in suggest(t['key'],pool):suggestions.append({'for':t['text'],'word':word})
    return {'query':described,'mode':mode,'total':len(items),'hits_total':sum(x['hit_count'] for x in items),'items':items[:limit],
        'suggestions':suggestions,'searched':len(pool)}


def export_docx(result,query,actor_name,when,filters=''):
    """The results as a Word document that can be handed over as evidence."""
    import io
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt, RGBColor
    doc=Document();style=doc.styles['Normal'];style.font.name='맑은 고딕';style.font.size=Pt(10.5)
    style.element.rPr.rFonts.set(qn('w:eastAsia'),'맑은 고딕')
    def write(paragraph,text,bold=False,mark=False,color=None,size=None):
        run=paragraph.add_run(text);run.bold=bold;run.font.name='맑은 고딕';run._element.rPr.rFonts.set(qn('w:eastAsia'),'맑은 고딕')
        if mark:run.font.highlight_color=WD_COLOR_INDEX.YELLOW
        if color:run.font.color.rgb=RGBColor(*color)
        if size:run.font.size=Pt(size)
        return run
    write(doc.add_paragraph(),'회의록 검색 근거 자료',bold=True,size=18)
    info=doc.add_table(rows=0,cols=2);info.style='Table Grid'
    def widths(table,first,second):
        table.autofit=False
        for row in table.rows:row.cells[0].width=Cm(first);row.cells[1].width=Cm(second)
    words=', '.join(t['text']+(' (함께 찾은 말: '+', '.join(t['also'])+')' if t['also'] else '') for t in result['query']['terms'])
    for label,value in [('검색어',query),('찾은 단어',words),('검색 조건',filters or '전체 프로젝트, 전체 기간'),('결과',f"회의록 {result['total']}건, 문장 {result['hits_total']}개"),('작성',f'{actor_name} · {when}')]:
        cells=info.add_row().cells;write(cells[0].paragraphs[0],label,bold=True);write(cells[1].paragraphs[0],value)
    widths(info,3,13)
    note=doc.add_paragraph();note.paragraph_format.space_before=Pt(8)
    write(note,'아래 문장은 등록된 회의록 원문에서 그대로 옮긴 것입니다. AI가 요약하거나 고쳐 쓴 문장은 포함하지 않았습니다.'+(' 입력한 단어를 모두 포함한 회의록이 없어, 일부 단어만 포함한 회의록을 실었습니다.' if result['mode']=='any' else ''),color=(0x52,0x67,0x7E),size=9.5)
    for number,item in enumerate(result['items'],1):
        head=doc.add_paragraph();head.paragraph_format.space_before=Pt(14);head.paragraph_format.keep_with_next=True
        write(head,f"{number}. {item['title']}",bold=True,size=12.5)
        meta=doc.add_paragraph();meta.paragraph_format.keep_with_next=True
        write(meta,f"회의일 {item['date'] or '날짜 없음'} · 프로젝트 {item['project_name']} · 일치 문장 {item['hit_count']}개",color=(0x52,0x67,0x7E),size=9.5)
        if not item['hits']:
            write(doc.add_paragraph(),'회의 제목에 검색어가 있습니다. 본문에는 일치하는 문장이 없습니다.',size=9.5);continue
        table=doc.add_table(rows=1,cols=2);table.style='Table Grid'
        write(table.rows[0].cells[0].paragraphs[0],'줄',bold=True);write(table.rows[0].cells[1].paragraphs[0],'원문',bold=True)
        for hit in item['hits']:
            cells=table.add_row().cells;write(cells[0].paragraphs[0],str(hit['no']))
            for text,matched in hit['segments']:write(cells[1].paragraphs[0],text,bold=matched,mark=matched)
        widths(table,1.5,14.5)
        if item['hit_count']>len(item['hits']):write(doc.add_paragraph(),f"이 회의록의 일치 문장 {item['hit_count']}개 중 {len(item['hits'])}개를 실었습니다.",color=(0x52,0x67,0x7E),size=9)
    if result['total']>len(result['items']):write(doc.add_paragraph(),f"회의록 {result['total']}건 중 {len(result['items'])}건을 실었습니다. 조건을 좁혀 다시 검색해 주세요.",color=(0x52,0x67,0x7E),size=9.5)
    buffer=io.BytesIO();doc.save(buffer);return buffer.getvalue()
