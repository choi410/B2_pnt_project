"""Add what newer analyses store to meetings analysed earlier: the standard-format layout of
free-form minutes and the AI summary.

Run from b2-service while the AI engine is up (the service may keep running):
  ..\\b2-model\\.venv\\Scripts\\python.exe -m work.v3.ai_backfill [data dir] [engine url] [--dry]
Only finished analyses are touched, and only the parts missing for the current revision.
Each meeting is written in its own short transaction, and only if it was not edited or
re-analysed while the model was answering. --dry prints the results without writing.
"""
import json, os, sqlite3, sys
from pathlib import Path


def main():
    args = [a for a in sys.argv[1:] if a != '--dry']; dry = '--dry' in sys.argv
    root = Path(__file__).resolve().parents[2]
    data = Path(args[0]) if args else root / 'data' / 'v5'
    url = args[1] if len(args) > 1 else 'http://127.0.0.1:8786'
    os.environ.update(B2_ENGINE_URL=url, B2_STAGE_LOCAL='1', B2_LLAMA_DISABLE='1')
    sys.path[:0] = [str(root), str(root.parent / 'b2-model')]
    sys.stdout.reconfigure(encoding='utf-8')
    import runtime
    runtime.ENGINE_URL = url
    from work.v3 import brief, freeform
    from work.v3.outline import build
    db = sqlite3.connect(f'file:{data / "workspace.sqlite3"}?mode=ro', uri=True) if dry else sqlite3.connect(data / 'workspace.sqlite3', timeout=30, isolation_level=None)
    rows = [json.loads(p) for (p,) in db.execute("select payload from records where kind='meeting'")]
    current = lambda m, key: m.get(key) is not None and m[key].get('revision') == m.get('revision')
    done = skipped = 0; lines_written = lines_offered = 0
    for m in sorted(rows, key=lambda m: m.get('date') or ''):
        if m.get('deleted_at') or not m.get('lines') or m.get('analysis_state') != 'ready':
            skipped += 1; continue
        rev = m.get('revision'); new = {}
        if freeform.is_free_form(m['lines']) and not current(m, 'layout'):
            placed = freeform.assign(m['lines'])
            if placed is not None:
                new['layout'] = {'items': placed, 'v': freeform.VERSION, 'revision': rev}
        layout = new.get('layout') or (m.get('layout') if current(m, 'layout') else None)
        if 'layout' in new or not current(m, 'brief'):
            view = build({**m, **new, 'outline_edits': {}})
            written = brief.write(view)
            if written is not None:
                new['brief'] = {'items': written, 'v': brief.VERSION, 'revision': rev}
        if not new:
            skipped += 1; continue
        print(f"== {m.get('date')} {m['title'][:34]} | " + ', '.join(f"{k} {len(v['items'])}" for k, v in new.items()))
        for x in (new.get('brief') or {}).get('items') or []:
            print('   -', x['text'], x['ids'])
        lines_written += len((new.get('brief') or {}).get('items') or [])
        if dry:
            done += 1; continue
        db.execute('BEGIN IMMEDIATE')
        (payload,) = db.execute("select payload from records where kind='meeting' and id=?", (m['id'],)).fetchone()
        now = json.loads(payload)
        if now.get('revision') == rev and now.get('analysis_state') == 'ready':
            now.update(new)
            db.execute("update records set payload=? where kind='meeting' and id=?", (json.dumps(now, ensure_ascii=False), m['id']))
            done += 1
        else:
            skipped += 1
        db.execute('COMMIT')
    print(f"{'would update' if dry else 'updated'} {done}, skipped {skipped}, summary lines kept {lines_written}")


if __name__ == '__main__':
    main()
