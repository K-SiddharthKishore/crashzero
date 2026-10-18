"""Event matching and clip metrics; dataset and deployment scopes stay separate."""
import math
import statistics


def summarize(rows, scope):
    if scope not in ('synthetic','dataset','deployment-camera'): raise ValueError('Explicit evaluation scope required.')
    tp=fp=fn=0; clip_tp=clip_fp=clip_tn=clip_fn=0; seconds=negative_seconds=0.;delays=[]
    for row in rows:
        duration=float(row['duration_seconds'])
        if not math.isfinite(duration) or duration<=0: raise ValueError('Positive finite duration required.')
        truth=row['events']; predictions=row['predictions'];used=set()
        seconds+=duration
        if not truth: negative_seconds+=duration
        for prediction in sorted(predictions,key=lambda p:p['timestamp']):
            candidates=[(abs(prediction['timestamp']-event['onset']),i) for i,event in enumerate(truth)
                        if i not in used and event['onset']-1<=prediction['timestamp']<=event['end']+1]
            if candidates:
                _,index=min(candidates);used.add(index);tp+=1
                delays.append(prediction.get('verified_at',prediction['timestamp'])-truth[index]['onset'])
            else: fp+=1
        fn+=len(truth)-len(used)
        clip_tp+=bool(truth) and bool(predictions)
        clip_fp+=not truth and bool(predictions)
        clip_tn+=not truth and not predictions
        clip_fn+=bool(truth) and not predictions
    precision=tp/(tp+fp) if tp+fp else None
    recall=tp/(tp+fn) if tp+fn else None
    f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
    return {'scope':scope,'event_tp':tp,'event_fp':fp,'event_fn':fn,
        'precision':precision,'recall':recall,'f1':f1,
        'clip_confusion_matrix':{'tp':clip_tp,'fp':clip_fp,'tn':clip_tn,'fn':clip_fn},
        'video_hours':seconds/3600,'negative_hours':negative_seconds/3600,
        'false_accident_alerts_per_video_hour':fp/(seconds/3600) if seconds else None,
        'median_detection_delay_seconds':statistics.median(delays) if delays else None,
        'positive_events':tp+fn,'clips':len(rows),
        'limitations':'Evaluation of this labelled sample only. Not deployment accuracy.' if scope!='deployment-camera' else 'Applies only to the evaluated camera conditions.'}
