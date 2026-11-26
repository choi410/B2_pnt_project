"""The team meeting-list search uses its existing review visibility rules."""
def review_pending(w,c):
    meetings={m['id']:m for m in w.all_records(c,'meeting')}
    pending={mid for mid,m in meetings.items() if m.get('analysis_state') in ('queued','running','failed')}
    for event in w.all_records(c,'change_event'):
        meeting=meetings.get(event['meeting_id'])
        if meeting and not event.get('superseded_by_revision') and event.get('source_revision')==meeting.get('revision') and event.get('review_state') not in ('확인됨','제외'):
            pending.add(meeting['id'])
    return pending
