"""Shared, read-only access to authorized project records and original text.

None means all accessible records; an explicit empty list means no records.
Each call rechecks access. Model-proposed identifiers have no special authority.
"""
from fastapi import HTTPException
from work.v17 import questions, retrieval


class ReadTools:
    def __init__(self, w, c, actor):
        self.w, self.c, self.actor = w, c, actor

    def projects(self, project_ids=None):
        projects = [p for p in self.w.all_records(self.c, 'project')
                    if not p.get('deleted_at') and self.actor['id'] in p['members']]
        if project_ids is None:
            return projects
        by_id = {p['id']:p for p in projects}
        if any(pid not in by_id for pid in project_ids):
            raise HTTPException(404, '현재 조회할 수 없는 프로젝트입니다.')
        return [by_id[pid] for pid in dict.fromkeys(project_ids)]

    def meetings(self, project_ids=None, *, meeting_ids=None):
        projects = self.projects(project_ids)
        ids = {p['id'] for p in projects}
        if meeting_ids is None:
            return questions.corpus(self.w, self.c, ids)
        docs = []
        for mid in dict.fromkeys(meeting_ids):
            record = self.w.read(self.c, 'meeting', mid)
            doc = retrieval.registered_document(record)
            if not doc or doc['project_id'] not in ids:
                raise HTTPException(404, '현재 조회할 수 없는 회의록입니다.')
            docs.append(doc)
        return docs

    def original(self, meeting_id, *, fingerprint=None, line_ids=None):
        doc = self.meetings(meeting_ids=[meeting_id])[0]
        if fingerprint is not None and doc['fingerprint'] != fingerprint:
            raise HTTPException(409, '회의록이 변경되었습니다. 원문을 다시 조회해 주세요.')
        lines = retrieval.document_lines(doc)
        if line_ids is not None:
            by_id = {line['id']:line for line in lines}
            if any(lid not in by_id for lid in line_ids):
                raise HTTPException(409, '원문 근거 문장을 다시 확인해 주세요.')
            lines = [by_id[lid] for lid in dict.fromkeys(line_ids)]
        return {k:v for k,v in doc.items() if k != 'body'} | {'lines':lines}

    def changes(self, project_ids=None):
        from work.v3.project_facts import active_changes
        return active_changes(self.w, self.c, self.projects(project_ids))

    def lookup(self, project_ids, intent, scope):
        from work.v3.metadata_questions import answer
        return answer(self.w, self.c, self.projects(project_ids), intent, scope)
