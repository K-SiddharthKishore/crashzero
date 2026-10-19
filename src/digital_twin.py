"""Observed, calibration-gated top-down junction rendering."""
from collections import deque
import cv2
import numpy as np


class DigitalTwin:
    def __init__(self, calibration):
        self.calibration = calibration
        self.trails = {}

    def update(self, tracks, timestamp):
        observed = []
        for track in tracks.values():
            if track.road_position is None:
                continue
            trail = self.trails.setdefault(track.id, deque(maxlen=40))
            if not trail or trail[-1][0] != timestamp:
                trail.append((timestamp, track.road_position))
            observed.append({"id": track.id, "class": track.cls, "position": track.road_position,
                             "velocity": track.road_velocity, "trail": [p for _, p in trail]})
        active = set(tracks)
        self.trails = {key: value for key, value in self.trails.items() if key in active}
        return observed

    def render(self, observed, hotspots=(), size=640):
        """Render only mapped observations; empty map is an honest empty state."""
        canvas = np.full((size, size, 3), (247, 249, 251), np.uint8)
        if self.calibration is None or self.calibration.matrix is None:
            cv2.putText(canvas, "CALIBRATION REQUIRED", (130, 315), cv2.FONT_HERSHEY_SIMPLEX, .8, (75, 92, 110), 2)
            return canvas
        points = np.asarray(self.calibration.road_points, float)
        low, high = points.min(0), points.max(0)
        span = np.maximum(high - low, .001)
        def xy(point):
            p = (np.asarray(point) - low) / span
            return int(50 + p[0] * (size - 100)), int(size - 50 - p[1] * (size - 100))
        polygon = np.asarray([xy(p) for p in points], np.int32)
        cv2.fillPoly(canvas, [polygon], (222, 230, 235))
        cv2.polylines(canvas, [polygon], True, (92, 111, 126), 2)
        for hotspot in hotspots:
            if hotspot.get("map_position") is None:
                continue
            center = xy(hotspot["map_position"])
            radius = int(18 + min(42, hotspot.get("count", 1) * 5))
            cv2.circle(canvas, center, radius, (40, 65, 235), -1)
            cv2.circle(canvas, center, radius + 10, (0, 170, 255), 2)
        for item in observed:
            trail = item["trail"]
            if len(trail) > 1:
                cv2.polylines(canvas, [np.asarray([xy(p) for p in trail], np.int32)], False, (89, 171, 191), 2)
            center = xy(item["position"])
            cv2.circle(canvas, center, 10, (32, 135, 206), -1)
            cv2.putText(canvas, f"{item['class']} #{item['id']}", (center[0] + 12, center[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, .42, (26, 50, 70), 1, cv2.LINE_AA)
        cv2.putText(canvas, "OBSERVED TOP-DOWN MAP", (18, 30), cv2.FONT_HERSHEY_SIMPLEX, .62, (22, 78, 110), 2)
        return canvas
