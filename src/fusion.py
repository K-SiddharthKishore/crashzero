from config.settings import DEFAULT_WEIGHTS

def fuse(historical=None,predictive=None,live=None,weights=None):
    values={'historical':historical,'predictive':predictive,'live':live}; weights=weights or DEFAULT_WEIGHTS
    active={k:float(v) for k,v in values.items() if v is not None and weights.get(k,0)>0}
    total=sum(weights[k] for k in active)
    if not total: return {'score':None,'weights':{},'contributions':{}}
    normalized={k:weights[k]/total for k in active}
    contributions={k:active[k]*normalized[k] for k in active}
    return {'score':round(sum(contributions.values()),1),'weights':normalized,'contributions':contributions}
