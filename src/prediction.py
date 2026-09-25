"""Predict any injury GIVEN a reported crash; never crash occurrence."""
import json
import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
from sklearn.metrics import roc_auc_score, brier_score_loss
from config.settings import ROOT, category
FEATURES=['borough','hour','weekday','vehicle']

def train(df):
    train_df=df[df.date<'2024-10-01']; test=df[df.date>='2024-10-01']
    if len(train_df)<100 or len(test)<100 or train_df.injury.nunique()<2:
        raise ValueError('Insufficient labeled history for temporal evaluation.')
    model=Pipeline([('features',ColumnTransformer([('cats',OneHotEncoder(handle_unknown='ignore'),['borough','vehicle']),('num','passthrough',['hour','weekday'])])),
        ('rf',RandomForestClassifier(n_estimators=100,max_depth=10,min_samples_leaf=40,random_state=42,n_jobs=4))])
    model.fit(train_df[FEATURES],train_df.injury)
    p=model.predict_proba(test[FEATURES])[:,1]; base=float(train_df.injury.mean())
    metrics={'target':'P(any injury or fatality | reported crash, selected context)',
        'training_period':'2024-01-01 to 2024-09-30','test_period':'2024-10-01 to 2024-12-31',
        'train_rows':len(train_df),'test_rows':len(test),'roc_auc':round(float(roc_auc_score(test.injury,p)),4),
        'brier':round(float(brier_score_loss(test.injury,p)),4),'baseline_brier':round(float(brier_score_loss(test.injury,np.full(len(test),base))),4),
        'training_injury_rate':round(base,4),'test_injury_rate':round(float(test.injury.mean()),4),
        'limitations':'Not a crash-occurrence forecast. No non-crash controls, traffic exposure, weather or live conditions. Temporal holdout only; no Bengaluru validation. Probability estimates are not independently calibrated.',
        'features':FEATURES,'random_seed':42}
    ROOT.joinpath('models').mkdir(exist_ok=True)
    joblib.dump(model,ROOT/'models/injury_model.joblib')
    (ROOT/'models/model_metrics.json').write_text(json.dumps(metrics,indent=2))
    return model,metrics

def load_or_train(df):
    path=ROOT/'models/injury_model.joblib'; metrics=ROOT/'models/model_metrics.json'
    if path.exists() and metrics.exists(): return joblib.load(path),json.loads(metrics.read_text())
    return train(df)

def timeline(model,borough,weekday,vehicle):
    x=pd.DataFrame({'borough':[borough]*24,'weekday':[weekday]*24,'hour':list(range(24)),'vehicle':[vehicle]*24})
    x['score']=np.round(model.predict_proba(x[FEATURES])[:,1]*100,6)
    x['category']=x.score.map(category)
    return x
