"""Generate explicitly labeled offline engineering fixtures, not accident footage."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import json
import subprocess
import cv2
import numpy as np
import imageio_ffmpeg
from src.video.simulation import SCENARIOS,scene
from config.settings import ROOT

def main():
    out=ROOT/'data/simulations';out.mkdir(exist_ok=True)
    for name in SCENARIOS:
        raw=out/(name+'_raw.mp4'); final=out/(name+'.mp4')
        writer=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*'mp4v'),12,(960,540)); rows=[]
        for k in range(144):
            t=k/12;detections=scene(name,t);rows.append(detections)
            frame=np.full((540,960,3),(25,28,30),np.uint8)
            cv2.line(frame,(0,330),(960,330),(95,95,95),2)
            cv2.putText(frame,'SYNTHETIC TEST / SCRIPTED TRACKS / NOT REAL FOOTAGE',(30,100),cv2.FONT_HERSHEY_SIMPLEX,.65,(90,205,245),2)
            cv2.putText(frame,name.replace('_',' ').upper(),(30,140),cv2.FONT_HERSHEY_SIMPLEX,.7,(230,230,230),1)
            for d in detections:
                x1,y1,x2,y2=map(int,d['box']);cv2.rectangle(frame,(x1,y1),(x2,y2),(140,180,150),-1)
            writer.write(frame)
        writer.release()
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-v','error','-y','-i',str(raw),'-c:v','libx264','-pix_fmt','yuv420p',str(final)],check=True)
        raw.unlink();final.with_suffix('.json').write_text(json.dumps({'kind':'SYNTHETIC_DETECTION_FIXTURE','fps':12,'detections':rows}))
        print(final.name)
if __name__=='__main__':main()
