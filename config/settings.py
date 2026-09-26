from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'models/yolo11n.pt'
ROAD_CLASSES = [0, 1, 2, 3, 5, 7]
HORIZON = 2.5
HISTORY_SECONDS = 1.2
MIN_HISTORY_SECONDS = 0.4
MIN_OBSERVATIONS = 5
MAX_TRACK_GAP = 0.5
HIGH_RISK = 61
CRITICAL_RISK = 81
RESOLVE_SECONDS = 0.5
COOLDOWN_SECONDS = 3.0
DEFAULT_WEIGHTS = {'historical': .25, 'predictive': .30, 'live': .45}
COLORS = {'LOW':'#67e8b5', 'MODERATE':'#f6cf6b', 'HIGH':'#ff985b', 'CRITICAL':'#ff5d78'}
def category(score):
    if score is None: return 'UNAVAILABLE'
    return 'LOW' if score <= 30 else 'MODERATE' if score <= 60 else 'HIGH' if score <= 80 else 'CRITICAL'
