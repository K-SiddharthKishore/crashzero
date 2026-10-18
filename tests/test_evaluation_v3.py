import pytest
from src.evaluation import summarize


def test_event_matching_duplicates_exposure_and_delay():
    rows=[{'duration_seconds':1800,'events':[{'onset':10,'end':12}],
        'predictions':[{'timestamp':10,'verified_at':12},{'timestamp':11,'verified_at':13}]},
        {'duration_seconds':1800,'events':[],'predictions':[]}]
    report=summarize(rows,'dataset')
    assert report['event_tp']==1 and report['event_fp']==1
    assert report['false_accident_alerts_per_video_hour']==1
    assert report['precision']==.5 and report['recall']==1
    assert report['median_detection_delay_seconds']==2
    assert report['clip_confusion_matrix']=={'tp':1,'fp':0,'tn':1,'fn':0}
    assert report['scope']=='dataset'


def test_no_positives_does_not_invent_precision_recall():
    report=summarize([{'duration_seconds':60,'events':[],'predictions':[]}],'deployment-camera')
    assert report['precision'] is None and report['recall'] is None and report['f1'] is None
    assert report['false_accident_alerts_per_video_hour']==0
