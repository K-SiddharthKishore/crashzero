from pathlib import Path
import urllib.request
root=Path(__file__).resolve().parents[1]
p=root/'models/yolo11n.pt'
if not p.exists():
    urllib.request.urlretrieve('https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt',p)
print(p)
