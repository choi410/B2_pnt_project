"""Project-local terminology with original-line provenance, never global aliases.

Only explicit label/alias notation is accepted. Parenthesized values, units,
states and explanatory clauses are not aliases. Callers provide an already
authorized, revision-checked and date-filtered registered corpus.
"""
import re
from work.v17.evidence_text import normalized, content_line, topic_terms
from work.v17.retrieval import document_lines

LABEL = r'[가-힣A-Za-z][가-힣A-Za-z ·_-]{1,34}'
QUALIFIER = re.compile(r'미정|보류|예정|검토|확인|진행|완료|요청|확정|신규|기존|단위|제외|포함|이상|이하|[0-9℃%±/]|(?:은|는|를|을)\s|니다|한다|했다')


def label(value):
    value=re.sub(r'\s+',' ',value).strip(' ·_-')
    return value if 2<=len(value)<=35 and len(value.split())<=5 and not QUALIFIER.search(value) else ''


def catalog(docs):
    groups={};fields=set()
    for doc in docs:
        for row in document_lines(doc):
            if not content_line(row['text']):continue
            text=re.sub(r'^\s*(?:[-*•]|\d+[.)])\s*','',row['text'])
            colon=re.match(r'^('+LABEL+r')[:：]',text)
            if colon and (name:=label(colon[1])):fields.add(name)
            # Anchoring at the start avoids treating an arbitrary parenthetical
            # explanation within a sentence as a term definition.
            pair=re.match(r'^('+LABEL+r')\s*\(([^()\n]{2,75})\)(?=\s|[:：은는이가의]|$)',text)
            if not pair:continue
            name=label(pair[1])
            # A common explicit definition: 원명(English Full Name, 이하 ABC).
            # The abbreviation is read from the source, never supplied by a list.
            parts=re.split(r'[,;]\s*이하\s+',pair[2])
            aliases=[label(part) for part in parts]
            if not name or any(not a for a in aliases):continue
            aliases=[a for a in aliases if normalized(a)!=normalized(name)]
            if not aliases:continue
            key=normalized(name)
            group=groups.setdefault(key,{'name':name,'variants':[name],'evidence':[]})
            for alias in aliases:
                if alias not in group['variants']:group['variants'].append(alias)
            group['evidence'].append({'meeting_id':doc.get('meeting_id'),'revision':doc.get('revision'),
                                     'date':doc.get('date'),'line_id':row['id']})
            fields.add(name)
    return list(groups.values()),fields


def pattern(term):
    return r'(?<![가-힣A-Za-z0-9])'+r'\s*'.join(re.escape(c) for c in term if not c.isspace())+r'(?=$|[^가-힣A-Za-z0-9]|은|는|이|가|을|를|의|에서|으로|변경)'


def resolve(question,docs):
    groups,fields=catalog(docs)
    matches=[]
    for group in groups:
        for variant in group['variants']:
            for match in re.finditer(pattern(variant),question,re.I):
                matches.append((match.start(),match.end(),group))
    # The same shorthand must not silently identify two different attributes.
    for start,end,group in matches:
        rivals={g['name'] for a,b,g in matches if a<end and start<b}
        if len(rivals)>1:
            return {'question':question,'terms':topic_terms(question),'subjects':[],
                    'message':'같은 표현으로 기록된 항목이 여러 개입니다. '+', '.join(sorted(rivals))+' 중 어느 항목을 볼까요?','notice':''}
    chosen=[];occupied=set();rewritten=question
    for start,end,group in sorted(matches,key=lambda x:(x[0],x[1]-x[0]),reverse=True):
        if any(i in occupied for i in range(start,end)):continue
        occupied.update(range(start,end));chosen.append(group)
        rewritten=rewritten[:start]+group['name']+rewritten[end:]
    chosen=list({normalized(g['name']):g for g in chosen}.values())
    # A parenthesized alias is one attribute, not several independently optional
    # words. Keep OR within an alias group and AND between different attributes.
    subject_text=rewritten
    for group in chosen:subject_text=re.sub(pattern(group['name']),' ',subject_text,flags=re.I)
    terms=[list(dict.fromkeys(normalized(v) for v in g['variants'])) for g in chosen]+topic_terms(subject_text)
    notice=''
    if chosen:
        notice='원문에 함께 표기된 용어('+ '; '.join(' / '.join(g['variants']) for g in chosen)+')를 함께 조회했습니다.'
    return {'question':rewritten,'terms':terms,'subjects':chosen,'message':'','notice':notice}
