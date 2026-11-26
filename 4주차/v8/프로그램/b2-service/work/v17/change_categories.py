"""Category metadata is independent of source-backed business and review states."""
import re
import unicodedata

BASE_CATEGORIES = ('요구사항', '사양', '납기', '미분류')
LABELS = {'요구사항': '고객 요구', '사양': '사양·성능', '납기': '일정·납기', '미분류': '미분류'}


def name_key(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', str(value or ''))).casefold()


def clean_name(value):
    value = ' '.join(str(value or '').split())
    aliases = {name_key(v): k for k, v in LABELS.items()}
    aliases.update({name_key(k): k for k in BASE_CATEGORIES})
    return aliases.get(name_key(value), value)


def category_names(topics=(), extra=()):
    return list(dict.fromkeys([*BASE_CATEGORIES, *[clean_name(x) for x in extra if x],
                              *[clean_name(t.get('category')) for t in topics if t.get('category')]]))


def extraction_category(value, topics=(), extra=()):
    """An unknown model label cannot discard an otherwise grounded record."""
    value = clean_name(value)
    return value if value in category_names(topics, extra) else '미분류'


def subject_name(value):
    return re.sub(r'[\s·_().\-]', '', str(value or '')).casefold()
