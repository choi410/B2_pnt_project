"""Text-only relevance helpers. Never modify stored documents or line identities."""
import re

META = re.compile(r'^\s*(?:[|#*\s]*)(?:회의명|회의\s*제목|회의일(?:시)?|일시|장소|프로젝트(?:명)?|고객사|참석자|작성자|작성일)\s*[:：|]')
HEAD = re.compile(r'^\s*(?:\d+[.)]\s*)?(?:회의록|회의\s*(?:개요|정보|안건)|핵심\s*요약|주요\s*논의|논의\s*내용|결정\s*사항|후속\s*조치|추가\s*확인|변경\s*사항)\s*[:：]?\s*$')
ALIASES = {'슬라이딩':'슬라이드', '납품일':'납기', '납기일':'납기', '납품':'납기', '개폐':'커버', '개정본':'개정'}
STOP = '''회의록 회의 프로젝트 기록 등록 자료 내용 관련 대한 대해 해당 논의한 논의된 논의 다룬 다뤘던 다룬것 이야기 전체 전부 모두 모든 처음부터 첫 처음 최근 최신 마지막 날짜순 오래된순 최신순 날짜 순서대로 순서 순으로 기준 당시 현재 지금 언제 얼마 얼마로 어떤 어떻게 무엇 뭐 뭐야 뭔가요 있었어 있었지 있었나 있나요 있어 있는 정한 정해진 합의돼 합의되어 확정돼 확정됐다는 확정된 합의된 정해져 하기로 상태 변경 과정 경위 설명 설명해줘 설명해주세요 찾아줘 찾아주세요 보여줘 보여주세요 알려줘 알려주세요 확인해줘 확인해주세요 검색 목록 리스트 제일 가장 그럼 그러면 이전 이후 시점 근거 끝났어 끝났나 끝났나요 끝났는지 완료됐어 완료되었어 완료됐나요 끝난 완료 완료여부 반영 완료했어 했어 했나 했었나 되었어 됐어 해줘 주세요 부탁해 요약 정리 결정 요청 승인 합의 확정 유지 여부 얼마였어 얼마였지 어디서 어디까지 다 이라는 라는 이라고 라고 인가 인지 맞아 맞나요 맞는지 맞는거야 나왔어 나왔나요 들어갔어 들어갔나요'''.split()
STOP += '이력 내역 상황 사항 변동 바뀐 달라진 누가 누구 거야 건가요 건지 것인지 승인된 결정된'.split()


def normalize_request(question):
    """Separate a requested operation from the topic; never rewrite source text."""
    q=re.sub(r'(?:변경|변동)\s*(?:상황|사항|내용|내역|이력|과정|경위)|(?:바뀐|달라진)\s*(?:내용|사항|부분|점)', ' 변경 이력 ', question)
    q=re.sub(r'어떻게\s*(?:바뀌었|변했|달라졌)(?:는지|나요|어|지)?', ' 변경 이력 ', q)
    q=re.sub(r'변경(?=\s*(?:알려|설명|정리|[?]))', '변경 이력 ', q)
    q=re.sub(r'(?:처음|초기)(?:이랑|과|하고)?\s*(?:현재|지금|최종)(?:의|이랑|과)?\s*(.*?)\s*(?:비교해줘|비교해\s*주세요)',r'\1 변경 이력',q)
    return re.sub(r'\s+', ' ', q).strip()


def normalized(text):
    text = text.lower()
    for a,b in ALIASES.items(): text=text.replace(a,b)
    return re.sub(r'\s+', '', text)


def metadata_question(question):
    return bool(re.search(r'작성자|참석자|누가\s*(?:썼|작성|참석)|작성한\s*사람|회의\s*장소|어디서\s*(?:회의|열)', question))


def topic_terms(question):
    q=re.sub(r'(?<!\d)(?:20\d{2}\s*(?:년|[-./])\s*)?\d{1,2}\s*(?:월|[-./])\s*\d{1,2}\s*일?', ' ', normalize_request(question.lower()))
    q=re.sub(r'(얼마|언제|무엇|뭐|누구|어디)(?:로)?(?:인가요|입니까|이었어|이었지|였어|였지|예요|이야|인지|야|지)(?=$|[^가-힣])',r' \1 ',q)
    q=re.sub(r'(?:어디|얼마|언제)(?:로|까지|부터)?(?=\s|[?!.]|$)',' ',q)
    q=re.sub(r'(?:맞지|맞아|어때|해|돼|말해줘|말해\s*주세요|좀|다시)(?=$|[^가-힣])',' ',q)
    q=re.sub(r'\d+\s*(?:건|개)|(?:첫|최근|마지막)\s*회의부터|날짜\s*순으로|처음부터', ' ', q)
    terms=[]
    for token in re.findall(r'[가-힣a-z0-9]+',q):
        if token in STOP or len(token)<2 or token.isdigit(): continue
        token=re.sub(r'(?:에서는|으로는|에서는|에서|에게|까지|부터|으로|인가요|였어|에는|은|는|을|를|이|가|의|에|로)$','',token)
        if len(token)<2 or token in STOP or token.isdigit(): continue
        if re.match(r'^(?:승인|확정|합의|결정)(?:된|돼|됐|되었|했|하였)',token):continue
        if re.match(r'^(?:바뀌었|달라졌|변했|변경됐|변경되었)',token):continue
        if re.match(r'^(?:찾아|보여|알려|설명|확인해|있었|되어|됐|끝났|완료됐|정했|합의돼|마쳤|마무리)',token):continue
        terms.append(normalized(token))
    return list(dict.fromkeys(terms))


def coverage(text, terms):
    value=normalized(text)
    return sum(any(v in value for v in t) if isinstance(t,(list,tuple)) else t in value for t in terms)/max(1,len(terms))


def content_line(text, question=''):
    return not HEAD.match(text) and (metadata_question(question) or not META.match(text)) and len(text.strip())>=5


def topic_lines(lines, question, terms=None):
    terms=topic_terms(question) if terms is None else terms
    return [line for line in lines if content_line(line['text'],question) and coverage(line['text'],terms)>0]
