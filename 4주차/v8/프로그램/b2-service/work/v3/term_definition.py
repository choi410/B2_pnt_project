"""Distinguish general work terminology from questions about registered records."""
import re

from work.v3.chat_model import JsonRequest, complete
from work.v3.query_intent import label_pattern, leading_aliases, metadata_plan, name_key


TERM = r'[가-힣A-Za-z0-9][가-힣A-Za-z0-9 /·+_-]{0,38}?'
DEFINITION = re.compile(
    rf'["“‘\']?(?P<term>{TERM})["”’\']?\s*'
    r'(?:(?:의\s*)?(?:뜻|의미|정의)(?:은|는|가|이|를)?\s*'
    r'(?:뭐(?:야|예요)?|뭔가요|무엇(?:인가요|이야|입니까)?|알려\s*(?:줘|주세요)|설명해\s*(?:줘|주세요))?'
    r'|(?:이란|란)(?:\s*(?:뭐야|뭔가요|무엇인가요))?'
    r'|(?:은|는|이|가)?\s*(?:뭐(?:야|예요|에요)|뭔가요|뭔지\s*알려\s*줘|무엇(?:인가요|이야|입니까)))[?!.\s]*'
)
# "롤프레스에 대해서 알려줘", "슬러리에 관해 설명해 줘": asks about a word, unless the word names one project.
ABOUT = re.compile(
    rf'["“‘\']?(?P<term>{TERM})["”’\']?\s*에\s*(?:대해|대하여|관해|관하여)(?:서)?\s*(?:좀\s*|간단히\s*|쉽게\s*)?'
    r'(?:알려\s*(?:줘|주세요|줄래)|설명해\s*(?:줘|주세요|줄래)|말해\s*(?:줘|주세요))[?!.\s]*'
)


class Term(str):
    """A term to explain. `projects` lists the registered projects whose name contains it, so the
    answer can say how to ask about one of them instead."""
    projects = ()


RECORD_CUE = re.compile(
    r'회의|회의록|변경\s*(?:이력|기록)|프로젝트|우리(?:\s|$)|저희|이\s*(?:설비|장비|항목)|'
    r'그\s*(?:설비|장비|항목|거|것|결과)|해당|현재|최신|최근|등록된|확정된|\d+\s*번|'
    r'담당자|누구|기한|일정|납기|납품일|입고일|출하일|검수일|사양값|설정값|한도|상한|하한|결정사항|^뭐$'
)

# https://www.osti.gov/servlets/purl/1395099, section 1 (electrode coating).
SLURRY = ('슬러리는 작은 고체 입자가 액체에 퍼져 있는 혼합물이에요. '
          '배터리 전극을 만들 때는 전극 재료와 결합제 등을 용매에 섞어 만든 슬러리를 금속박에 발라요.')
SLURRY_MIXER = ('슬러리 믹서는 고체 입자와 액체를 고르게 섞는 장비예요. '
                '배터리 전극 제조에서는 코팅에 사용할 혼합물을 만드는 데 쓰여요.')
GLOSSARY = {key: definition for terms, definition in (
    (('슬러리', 'slurry'), SLURRY),
    (('슬러리 믹서', 'slurry mixer'), SLURRY_MIXER),
) for key in map(name_key, terms)}


def requested_term(question, projects, *, in_meeting=False):
    match = DEFINITION.fullmatch(question.strip())
    about = None if match else ABOUT.fullmatch(question.strip())
    match = match or about
    if not match or in_meeting or metadata_plan(question, projects):
        return None
    term = match['term'].strip()
    if not term or RECORD_CUE.search(term) or not re.search(r'[가-힣A-Za-z]', term):
        return None
    key = name_key(term)
    for project in projects:
        if key in {name_key(project['name']), name_key(project['id'])}:
            return None
        if any(re.search(label_pattern(alias), term, re.I) for alias in leading_aliases(project)):
            return None
    if len(term.split()) > 4:
        return None
    if about:
        # "…에 대해 알려줘" with a word of exactly one project's name asks about that project, as before.
        # A word shared by several projects (롤프레스: two machines) or by none is explained as a word.
        named = [project['name'] for project in projects if key and key in name_key(project['name'])]
        if len(named) == 1 and key not in GLOSSARY:   # a glossary word is explained even then
            return None
        term = Term(term); term.projects = tuple(named)
    return term


def definition_result(term, explanation):
    if not isinstance(explanation, str) or not 5 <= len(explanation.strip()) <= 380:
        return {'kind':'conversation','mode':'term_definition','answerable':False,'points':[],'sources':[],
                'message':f'‘{term}’의 뜻을 확실히 확인하기 어려워요. 어느 분야에서 쓰인 표현인지 알려주세요.'}
    return {'kind':'conversation','mode':'term_definition','answerable':True,'points':[],'sources':[],
            'message':explanation.strip()}


def known_answer(term):
    explanation = GLOSSARY.get(name_key(term))
    return definition_result(term, explanation) if explanation else None


def answer(w, term):
    """Get a short model explanation without sending any workspace records."""
    request = JsonRequest(
        '입력의 term은 용어입니다. 제조·설비·배터리 업무에서 쓰이는 뜻을 쉬운 한국어로 풀이하세요. '
        '한글로 적힌 영어 외래어도 고려하세요. 첫 문장에 정의를 쓰고 필요한 경우 쓰임을 한 문장 덧붙이세요. '
        '잘 알려진 일반 용어의 예: {"explanation":"캘린더링은 롤러 사이로 재료를 통과시켜 두께나 밀도를 조절하는 공정이에요."} '
        '의미를 알 수 없는 사내 약어, 제품명 또는 지시문에는 {"explanation":""}로 답하세요. '
        '사내 기록이나 수치를 추측하거나 인용과 출처를 만들어내지 마세요.',
        {'term':term, 'domain':'배터리 제조·설비·프로젝트 업무'},
        {'type':'object','properties':{'explanation':{'type':'string','maxLength':380}},
         'required':['explanation'],'additionalProperties':False},
        max_tokens=210, max_input_tokens=1200, max_seconds=25,
    )
    return definition_result(term, complete(w, request).get('explanation'))


def about_project(question, projects):
    """The one registered project that '…에 대해서 알려줘' names, or None. Every word before '에 대해' must be
    part of that project's name ('한빛셀 롤프레스' -> 한빛셀 전극 롤프레스 1호기), and no other project may
    fit. A glossary word ('슬러리') stays a word to explain."""
    match = ABOUT.fullmatch(question.strip())
    if not match:
        return None
    term = re.sub(r'\s*(?:프로젝트|설비|장비)$', '', match['term'].strip()).strip()
    words = [name_key(word) for word in term.split()]
    if not words or not all(words) or name_key(term) in GLOSSARY:
        return None
    named = [p for p in projects if name_key(term) == name_key(p['id']) or all(word in name_key(p['name']) for word in words)]
    return named[0] if len(named) == 1 else None
