"""Persistent, deduplicated mapped conflict observations for hotspot analysis."""
from pathlib import Path
import json
import sqlite3
from datetime import datetime, timezone


class IntelligenceStore:
    def __init__(self, root):
        self.db = Path(root) / "intelligence.sqlite"
        self.db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db) as db:
            db.execute("""CREATE TABLE IF NOT EXISTS conflict_events (
                id TEXT PRIMARY KEY, created_at TEXT, camera_id TEXT, category TEXT,
                map_x REAL, map_y REAL, payload TEXT)""")
            db.execute("CREATE INDEX IF NOT EXISTS conflict_event_camera ON conflict_events(camera_id,created_at)")

    def save(self, event, camera_id, map_position):
        if map_position is None:
            return False
        event_id = event.setdefault("event_id", f"EV-{event.get('analysis_id','run')[:8]}-{event['timestamp']:.3f}")
        payload = {**event, "map_position": list(map_position)}
        with sqlite3.connect(self.db) as db:
            db.execute("BEGIN IMMEDIATE")
            result = db.execute("INSERT OR IGNORE INTO conflict_events VALUES (?,?,?,?,?,?,?)",
                       (event_id, datetime.now(timezone.utc).isoformat(), camera_id, event["state"],
                        float(map_position[0]), float(map_position[1]), json.dumps(payload)))
        return result.rowcount == 1

    def hotspots(self, camera_id=None, categories=None):
        query, args = "SELECT category,map_x,map_y,payload FROM conflict_events", []
        clauses = []
        if camera_id:
            clauses.append("camera_id=?"); args.append(camera_id)
        if categories:
            clauses.append("category IN (" + ",".join("?" * len(categories)) + ")"); args.extend(categories)
        if clauses: query += " WHERE " + " AND ".join(clauses)
        with sqlite3.connect(self.db) as db:
            rows = db.execute(query, args).fetchall()
        bins = {}
        for category, x, y, payload in rows:
            key = (round(x, 2), round(y, 2), category)
            value = bins.setdefault(key, {"map_position": [x, y], "category": category, "count": 0, "events": []})
            value["count"] += 1; value["events"].append(json.loads(payload))
        return sorted(bins.values(), key=lambda item: item["count"], reverse=True)
