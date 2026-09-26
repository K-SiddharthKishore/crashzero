from config.settings import MODEL, ROAD_CLASSES, ROOT
import os
from config.v2 import SAFETY
(ROOT/".cache/ultralytics").mkdir(parents=True,exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR",str(ROOT/".cache/ultralytics"))

class RoadDetector:
    def __init__(self,device='cpu',image_size=640,tracker=None,confidence=None):
        import torch
        from ultralytics import YOLO
        if not MODEL.exists():
            raise FileNotFoundError('YOLO weights missing. Run .venv/bin/python scripts/fetch_model.py once online.')
        torch.set_num_threads(4)
        self.model=YOLO(str(MODEL)); self.device=device; self.image_size=image_size
        self.tracker=tracker or str(ROOT/'config/bytetrack-v2.yaml')
        self.confidence=SAFETY.detection_confidence if confidence is None else confidence
    def track(self,frame):
        result=self.model.track(frame,persist=True,tracker=self.tracker,classes=ROAD_CLASSES,
            conf=self.confidence,iou=.5,imgsz=self.image_size,device=self.device,verbose=False)[0]
        boxes=result.boxes
        if boxes is None or boxes.id is None: return []
        return [{'id':int(tid),'class':result.names[int(cls)],'box':box.tolist(),'confidence':float(conf)}
            for tid,cls,box,conf in zip(boxes.id.cpu().numpy(),boxes.cls.cpu().numpy(),boxes.xyxy.cpu().numpy(),boxes.conf.cpu().numpy())]
