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

def draw_zone_labels(image,events,cell_size=120):
    import cv2
    if image is None: return image
    result=image.copy();h,w=result.shape[:2]
    for zone in conflict_zones(events,cell_size):
        x,y=(v*cell_size for v in zone['cell'])
        if not 0<=x<w or not 0<=y<h:continue
        color=(90,150,240) if zone['risk']=='HIGH' else (120,210,230)
        cv2.rectangle(result,(x,y),(min(x+cell_size,w-1),min(y+cell_size,h-1)),color,1)
        cv2.putText(result,zone['zone'],(x+5,max(16,y+18)),cv2.FONT_HERSHEY_SIMPLEX,.45,color,1,cv2.LINE_AA)
    return result
