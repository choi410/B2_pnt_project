"""Canonical PNT core-document formats and the two-stage analysis architecture."""

ARCHITECTURE = {
    'name': '하이브리드 듀얼 엔진',
    'description': '생성형 AI가 문서에서 후보 항목을 추출하고 결정형 규칙이 형식과 근거를 검증합니다.',
    'engines': [
        {
            'id': 'document-intelligence',
            'name': '문서 해석 엔진',
            'kind': '생성형 AI',
            'implementation': 'Qwen3-4B-Instruct-2507 4bit',
            'role': '회의록에서 고객 요구, 설계변경, 후속 조치와 원문 근거를 추출',
        },
        {
            'id': 'evidence-rules',
            'name': '근거 규칙 검증 엔진',
            'kind': '결정형 규칙',
            'implementation': 'Pydantic 스키마, 원문 근거, 날짜 및 상태 규칙',
            'role': '출력 형식, 근거 번호, 담당자와 기한, 상태 전이 및 미정 항목을 검증',
        },
    ],
}


DOCUMENT_FORMATS = [
    {
        'code': 'DOC-01',
        'title': '킥오프 미팅 기록서',
        'subtitle': 'KICKOFF MEETING MINUTES',
        'purpose': '회의 논의에서 고객 요구와 결정, 후속 조치를 분리해 기록합니다.',
        'sections': [
            {'name': '기본 정보', 'fields': ['프로젝트 번호·명', '고객사', '장비·호기', '회의일', '작성자', '문서 번호', '참석자']},
            {'name': '회의 안건 및 논의 내용', 'fields': ['자유 기술 원문']},
            {'name': '고객 요구 및 결정 사항', 'fields': ['요구번호', '요구·결정 내용', '확정 여부']},
            {'name': '후속 조치', 'fields': ['연결 요구번호', '할 일', '담당자', '기한']},
        ],
        'missing_rule': '담당자와 기한이 없으면 미정으로 기록',
    },
    {
        'code': 'DOC-02',
        'title': '설계 사양서',
        'subtitle': 'DESIGN SPECIFICATION',
        'purpose': '회의 요구번호를 기준으로 고객 요구값과 당사 적용값을 연결합니다.',
        'sections': [
            {'name': '기본 정보', 'fields': ['프로젝트 번호·명', '고객사', '장비·호기', '작성일', '작성자', '문서 번호', '도면 번호·개정']},
            {'name': '요구사항별 설계 사양', 'fields': ['요구번호', '부위·항목', '고객 요구값', '당사 적용값', '단위']},
            {'name': '측정 기준점 및 공차', 'fields': ['기준점', '공차 및 허용범위']},
            {'name': '검토 결과 및 미확정 사항', 'fields': ['검토 결과', '미확정 사양', '사양 상태', '검토자']},
        ],
        'missing_rule': '미확정 사양은 미정으로 표시',
    },
    {
        'code': 'DOC-03',
        'title': '설계변경 요청 및 검토서',
        'subtitle': 'DESIGN CHANGE REQUEST AND REVIEW',
        'purpose': '변경 전후 사양과 승인 상태, 실제 적용 상태를 분리합니다.',
        'sections': [
            {'name': '기본 정보', 'fields': ['프로젝트 번호·명', '고객사', '장비·호기', '작성일', '작성자', '문서 번호', '연결 요구번호', '현재 도면·개정']},
            {'name': '변경 전후 사양', 'fields': ['부위·항목', '기존 승인 사양', '요청 사양', '최종 승인 사양']},
            {'name': '변경 사유 및 근거', 'fields': ['변경 사유', '원문 및 첨부 근거']},
            {'name': '검토 결과 및 적용 호기·시점', 'fields': ['검토 결과', '적용 호기', '적용 시점', '승인 상태', '승인자·승인일']},
        ],
        'missing_rule': '요청, 승인, 현장 적용 상태를 서로 구분',
    },
    {
        'code': 'DOC-04',
        'title': '제작 및 조립 작업지시서',
        'subtitle': 'FABRICATION AND ASSEMBLY WORK ORDER',
        'purpose': '승인된 도면 개정을 기준으로 작업 지시와 수행 결과를 기록합니다.',
        'sections': [
            {'name': '기본 정보', 'fields': ['프로젝트 번호·명', '고객사', '장비·호기', '작업일', '작업자', '문서 번호', '적용 도면·개정', '관련 변경번호']},
            {'name': '작업 지시 및 수행 기록', 'fields': ['작업 항목', '작업 기준·참조 도면', '완료 여부']},
            {'name': '이상사항 및 조치', 'fields': ['이상사항', '조치 내용', '보류 사유', '확인자', '확인일']},
        ],
        'missing_rule': '보류된 작업은 사유를 기록',
    },
    {
        'code': 'DOC-05',
        'title': '검사 및 시운전 체크시트',
        'subtitle': 'INSPECTION AND COMMISSIONING CHECKLIST',
        'purpose': '승인 사양과 실측값을 비교하고 부적합 및 재검사 결과를 남깁니다.',
        'sections': [
            {'name': '기본 정보', 'fields': ['프로젝트 번호·명', '고객사', '장비·호기', '검사일', '검사자', '문서 번호', '적용 도면·개정', '측정기 번호']},
            {'name': '검사 결과', 'fields': ['요구번호·검사 항목', '판정 기준', '실측값·단위', '판정']},
            {'name': '이상사항 및 재검사 결과', 'fields': ['이상사항', '조치 내용', '재검사 결과', '종합 판정', '확인자·확인일']},
        ],
        'missing_rule': '미검사 항목은 미검사로 표시',
    },
]
