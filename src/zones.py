"""Camera image-space spatial bins from deduplicated V1 conflict coordinates."""
from collections import Counter

def conflict_zones(events,cell_size=120):
    bins={}
    for event in events:
        key=(int(event['x']//cell_size),int(event['y']//cell_size))
        bins.setdefault(key,[]).append(event)
    result=[]
    for key,rows in sorted(bins.items(),key=lambda item:len(item[1]),reverse=True):
        types=Counter(' ↔ '.join(sorted(e['classes'])) for e in rows)
        result.append({'zone':f'ZONE {len(result)+1:02d}', 'cell':key,'conflicts':len(rows),
            'near_misses':sum(e['status']=='prototype near miss' for e in rows),
            'risk':'HIGH' if len(rows)>=3 else 'MODERATE',
            'main_interaction':types.most_common(1)[0][0], 'events':rows,
            'trend':'Insufficient comparable observation windows'})
    return result
