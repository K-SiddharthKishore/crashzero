"""Transparent heuristic index, not a calibrated crash probability."""
import numpy as np
from config.settings import HORIZON

def interaction_score(ttc, separation, radius, convergence, stability, vulnerable):
    urgency = np.clip(1-ttc/HORIZON,0,1)
    proximity = np.clip(1-separation/(radius*1.4),0,1)
    approach = np.clip(convergence/max(radius,1),0,1)
    score = 100*(.40*proximity + .30*urgency + .20*approach + .10*int(vulnerable))
    return int(round(np.clip(score*(.55+.45*stability),0,100)))
