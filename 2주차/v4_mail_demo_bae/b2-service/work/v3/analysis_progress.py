"""Measured elapsed time and conservative estimates; never a simulated AI percent."""
from datetime import datetime,timezone
import math
from statistics import median


def stamp():return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def epoch(value):
    try:return datetime.fromisoformat(value).timestamp()
    except (TypeError,ValueError):return None


def elapsed(start,now):
    value=epoch(start)
    return max(0,now-value) if value is not None else None


def estimate_runtime(source,meetings,pipeline):
    size=len(source or '')
    if not size:return None
    samples=[]
    for m in sorted(meetings,key=lambda m:m.get('analysis_finished_at') or m.get('created_at',''),reverse=True):
        metrics=m.get('metrics') or {};passes=metrics.get('passes') or []
        old_size=metrics.get('source_chars') or len(m.get('source') or '')
        if m.get('analysis_state')!='ready' or m.get('analysis_stale') or not passes or not old_size:continue
        if any(p.get('pipeline')!=pipeline or p.get('cache_hit') or p.get('cold_start') for p in passes):continue
        if metrics.get('source_revision',m.get('revision'))!=m.get('revision'):continue
        if not .5<=size/old_size<=2:continue
        seconds=metrics.get('analysis_seconds')
        if seconds is None:seconds=(metrics.get('seconds') or 0)-(metrics.get('queue_seconds') or 0)
        seconds-=sum(p.get('model_load_seconds',0) for p in passes)
        if not 1<=seconds<=3600:continue
        # Input size matters, but fixed prompt/output work prevents linear scaling.
        samples.append(seconds*(.5+.5*size/old_size))
        if len(samples)>=30:break
    if len(samples)<3:return None
    values=sorted(samples);center=median(values)
    low=max(5,math.floor(min(values[len(values)//5],center)*.65/5)*5)
    high=max(low+10,math.ceil(max(values[min(len(values)-1,4*len(values)//5)],center)*1.6/5)*5)
    return {'low_seconds':low,'high_seconds':high,'sample_count':len(samples),'pipeline':pipeline}


def runtime_remaining(m,now):
    estimate=m.get('analysis_estimate')
    if m.get('analysis_phase') in ('loading','retrying'):return None,m['analysis_phase']
    if not estimate:return None,'insufficient'
    used=0
    if m.get('analysis_state')=='running':
        seconds=elapsed(m.get('analysis_started_at'),now)
        if seconds is None:return None,'insufficient'
        used=max(0,seconds-(m.get('analysis_loading_seconds') or 0))
    high=estimate['high_seconds']-used
    if high<=0:return None,'overdue'
    return [max(0,estimate['low_seconds']-used),high],'available'


def progress_snapshot(meetings,now=None):
    now=datetime.now(timezone.utc).timestamp() if now is None else now
    active=[m for m in meetings if not m.get('deleted_at') and m.get('analysis_state') in ('queued','running')]
    active.sort(key=lambda m:(0 if m['analysis_state']=='running' else 1,epoch(m.get('analysis_queued_at') or m.get('created_at')) or float('inf'),m['id']))
    result={};ahead=[]
    for m in active:
        queued=m['analysis_state']=='queued'
        own,status=runtime_remaining(m,now)
        remaining=own
        if queued and ahead:
            estimates=[runtime_remaining(previous,now)[0] for previous in ahead]
            if own is None or any(v is None for v in estimates):remaining=None;status='waiting_unknown'
            else:remaining=[own[i]+sum(v[i] for v in estimates) for i in (0,1)]
        result[m['id']]={
            'measured_at':datetime.fromtimestamp(now,timezone.utc).isoformat(),
            'elapsed_seconds':elapsed(m.get('analysis_queued_at') if queued else m.get('analysis_started_at'),now),
            'queue_ahead':len(ahead) if queued else 0,
            'estimate_status':status,
            'remaining_seconds':remaining,
        }
        ahead.append(m)
    return result


def recent_batch(meetings,actor_id):
    own=[m for m in meetings if m.get('author')==actor_id and m.get('registration_batch_id')]
    if not own:return None
    latest=max(own,key=lambda m:m.get('registration_batch_at') or m.get('created_at',''))
    batch=[m for m in own if m.get('registration_batch_id')==latest['registration_batch_id']]
    counts={'total':len(batch),'completed':0,'failed':0,'pending':0,'removed':0}
    for m in batch:
        key='removed' if m.get('deleted_at') else 'completed' if m.get('analysis_state')=='ready' and not m.get('analysis_stale') else 'failed' if m.get('analysis_state')=='failed' else 'pending'
        counts[key]+=1
    return {'id':latest['registration_batch_id'],**counts}
