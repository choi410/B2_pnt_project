"""Shadow-mode report: compare the tier shown at review time with what the person did.

Run from b2-service:  ..\\b2-model\\.venv\\Scripts\\python.exe -m work.v3.shadow_report [data dir]
Read-only. A record counts as "changed by a person" when it was excluded or edited.

Only records a person confirmed, excluded or edited ONE BY ONE (via=single, or an edit)
count as independent checks. Batch buttons (section, all, auto candidates) are listed
separately: a batch confirmation says nothing about whether the tier was right.
The number that matters before enabling automatic confirmation:
  auto-tier records, checked one by one, that a person excluded or edited (keep near zero).
Auto-tier spot-check samples are always left for one-by-one review, so this number keeps
being measured even when the "confirm auto candidates" button is used.
"""
import json,sqlite3,sys
from pathlib import Path

def main():
    data=Path(sys.argv[1]) if len(sys.argv)>1 else Path(__file__).resolve().parents[2]/'data'/'v5'
    c=sqlite3.connect(f"file:{data/'workspace.sqlite3'}?mode=ro",uri=True)
    rows=[json.loads(p) for (p,) in c.execute("select payload from records where kind='change_event'")]
    seen=[e for e in rows if e.get('shadow_tier')]
    single={};batch={};misses=[]
    for e in seen:
        s=e['shadow_tier'];tier=s.get('tier');changed=s.get('action') in ('제외','수정')
        independent=s.get('via','single')=='single' or s.get('action')=='수정'
        bucket=single if independent else batch
        bucket.setdefault(tier,{'kept':0,'changed':0})['changed' if changed else 'kept']+=1
        if independent and tier=='auto' and changed:
            misses.append((s.get('action'),s['record'].get('title'),s['record'].get('before'),s['record'].get('after'),s['record'].get('business_state')))
    print(f'records with a recorded review: {len(seen)} / all records: {len(rows)}')
    print('\nchecked one by one (independent):')
    for tier in ('auto','quick','human'):
        t=single.get(tier,{'kept':0,'changed':0});n=t['kept']+t['changed']
        print(f"  {tier:6} reviewed {n:4}  confirmed as is {t['kept']:4}  excluded/edited {t['changed']:4}"+(f'  ({t["changed"]/n:.1%})' if n else ''))
    vias={}
    for e in seen:
        s=e['shadow_tier']
        if not (s.get('via','single')=='single' or s.get('action')=='수정'):vias[s.get('via')]=vias.get(s.get('via'),0)+1
    print('\nconfirmed with a batch button (not counted above):',vias or 'none')
    if misses:
        print('\nauto-tier records a person excluded or edited (rules to tighten):')
        for m in misses:print('  ',m)

if __name__=='__main__':main()
