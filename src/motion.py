"""Image-space least-squares motion. No physical speed claim."""
import numpy as np

def estimate(history):
    a = np.asarray(history, dtype=float)
    t = a[:, 0] - a[-1, 0]
    design = np.column_stack([t, np.ones(len(t))])
    fit, *_ = np.linalg.lstsq(design, a[:, 1:3], rcond=None)
    residual = float(np.sqrt(np.mean((design @ fit - a[:, 1:3]) ** 2)))
    speed = float(np.linalg.norm(fit[0]))
    stability = float(np.clip(1 - residual / max(5, speed * .25), 0, 1))
    return fit[0], fit[1], stability
