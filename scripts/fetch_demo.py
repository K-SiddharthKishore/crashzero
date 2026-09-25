from pathlib import Path
import urllib.request,subprocess,json
import imageio_ffmpeg
root=Path(__file__).resolve().parents[1]
source=json.loads((root/'data/demo/source.json').read_text())
p=root/'data/demo/traffic.mp4'
if not p.exists():
    original=p.parent/'download_original.mp4'
    urllib.request.urlretrieve(source['download_url'],original)
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-i',str(original),'-t','35','-vf','scale=960:-2,fps=12','-an','-c:v','libx264','-crf','22',str(p)],check=True)
print(p)
