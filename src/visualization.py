import cv2
import numpy as np
from config.settings import HORIZON, HIGH_RISK

def draw(frame,tracks,interactions,t,near_count):
    high={tid for i in interactions if i['risk']>=HIGH_RISK for tid in i['ids']}
    h,w=frame.shape[:2]
    for tr in tracks.values():
        color=(91,152,255) if tr.id in high else (181,232,103)
        p1=(int(tr.box[0]),int(tr.box[1])); p2=(int(tr.box[2]),int(tr.box[3]))
        cv2.rectangle(frame,p1,p2,color,2)
        label=f'{tr.cls.upper()} #{tr.id}'
        cv2.putText(frame,label,(p1[0],max(74,p1[1]-5)),cv2.FONT_HERSHEY_SIMPLEX,.42,color,1,cv2.LINE_AA)
        pts=np.array([[int(x),int(y)] for _,x,y in (tr.smoothed_history or tr.history)],np.int32)
        if len(pts)>1: cv2.polylines(frame,[pts],False,color,2,cv2.LINE_AA)
        if tr.ready:
            for k in np.arange(0,HORIZON,.20):
                a=tuple(np.clip(tr.project(k),[-w,-h],[2*w,2*h]).astype(int))
                b=tuple(np.clip(tr.project(k+.10),[-w,-h],[2*w,2*h]).astype(int))
                cv2.line(frame,a,b,(242,193,84),2,cv2.LINE_AA)
    for i in interactions[:3]:
        if i['risk']<HIGH_RISK: continue
        center=(int(i['x']),int(i['y']))
        cv2.circle(frame,center,22,(110,85,255),2,cv2.LINE_AA)
        cv2.putText(frame,f"RISK {i['risk']} | ~{i['ttc']:.1f}s",(max(2,min(w-190,center[0]+25)),max(90,min(h-10,center[1]))),cv2.FONT_HERSHEY_SIMPLEX,.5,(110,85,255),2,cv2.LINE_AA)
    overlay=frame.copy(); cv2.rectangle(overlay,(0,0),(w,65),(22,15,8),-1)
    cv2.addWeighted(overlay,.9,frame,.1,0,frame)
    peak=max([i['risk'] for i in interactions],default=0)
    cv2.putText(frame,f'CRASHZERO  /  VISION INTELLIGENCE    {t:05.1f}s',(16,25),cv2.FONT_HERSHEY_SIMPLEX,.62,(245,245,245),1,cv2.LINE_AA)
    cv2.putText(frame,f'{len(tracks)} ACTIVE  |  RISK {peak}/100  |  {near_count} PROTOTYPE NEAR MISSES',(16,49),cv2.FONT_HERSHEY_SIMPLEX,.45,(181,232,103),1,cv2.LINE_AA)
    cv2.rectangle(frame,(0,h-28),(w,h),(22,15,8),-1)
    cv2.putText(frame,'SOLID: observed  /  DASHED: projected  /  Image-space estimates, not collision predictions',(10,h-10),cv2.FONT_HERSHEY_SIMPLEX,.37,(220,220,220),1,cv2.LINE_AA)
    return frame

def heatmap(frame,events):
    h,w=frame.shape[:2]; density=np.zeros((h,w),np.float32)
    for e in events:
        x,y=int(e['x']),int(e['y'])
        if 0<=x<w and 0<=y<h: density[y,x]+=1
    if density.max()==0: return frame
    density=cv2.GaussianBlur(density,(0,0),25)
    anchors=np.array([[181,232,103],[107,207,246],[91,152,255],[120,93,255]],dtype=float)
    lut=np.stack([np.interp(np.linspace(0,3,256),np.arange(4),anchors[:,c]) for c in range(3)],axis=1).astype('uint8').reshape(256,1,3)
    colors=cv2.applyColorMap((density/max(density.max(),1e-9)*255).astype('uint8'),lut)
    alpha=np.clip(density/max(density.max(),1e-9)*.75,0,.75)[...,None]
    return (frame*(1-alpha)+colors*alpha).astype('uint8')
