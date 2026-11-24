"""변경이력 2단계 승인: 참여자 1차 검수 → PM 최종 승인.

- 새로 등록하거나 원문을 고친 회의록은 approval_required=True가 된다.
- 참여자는 PM이 승인하기 전까지 확인·제외·수정할 수 있다.
- PM이 회의록(현재 원문 버전) 단위로 승인하면, 확인된 항목만 공식 변경이력이 된다.
- 승인 뒤 항목이 바뀌면(되돌리기·수정) 승인은 풀리고 다시 승인해야 한다.
- 이 기능 이전에 등록된 회의록(approval_required 없음)은 기존 규칙을 그대로 쓴다.
"""
import os


def enabled():
    """B2_CHANGE_APPROVAL=0이면 새 회의록도 승인 없이 기존 방식으로 반영한다."""
    return os.environ.get('B2_CHANGE_APPROVAL', '1').strip() != '0'


def required(m):
    return bool(m and m.get('approval_required'))


def approved(m):
    a = (m or {}).get('change_approval') or {}
    return bool(a) and a.get('revision') == (m or {}).get('revision')


def published(e, m):
    """AI 답변·변경이력 조회가 근거로 써도 되는 항목인가.

    기존 회의록: '제외'만 빼는 기존 규칙. 승인 대상 회의록: 확인됨 + 현재 버전 승인."""
    if not m or e.get('review_state') == '제외':
        return False
    if not required(m):
        return True
    return e.get('review_state') == '확인됨' and approved(m) and e.get('source_revision') == m.get('revision')


def listed(e, m):
    """변경이력 화면에 공식 기록으로 보일 항목(화면은 원래 확인됨만 보여 준다)."""
    return e.get('review_state') == '확인됨' and (not required(m) or approved(m))


def state(m, events):
    """화면 표시용: legacy | reviewing | pending | approved"""
    if not required(m):
        return 'legacy'
    current = [e for e in events if e.get('source_revision') == m.get('revision') and not e.get('superseded_by_revision')]
    if any(e.get('review_state') not in ('확인됨', '제외') for e in current):
        return 'reviewing'
    return 'approved' if approved(m) else 'pending'


def view(m, events):
    a = (m or {}).get('change_approval') or {}
    s = state(m, events)
    return {'state': s, 'by': a.get('by') if s == 'approved' else None, 'at': a.get('at') if s == 'approved' else None}


def revoke(m):
    """승인된 회의록의 항목이 바뀌면 승인을 푼다. 바뀌었으면 True."""
    if required(m) and approved(m):
        m['change_approval'] = None
        return True
    return False
