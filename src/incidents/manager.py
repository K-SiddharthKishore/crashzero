"""Bounded incident evidence capture and durable SQLite incident archive."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import shutil
import sqlite3
import subprocess

import cv2
import numpy as np

from config.settings import ROOT
from config.v2 import SAFETY


class DemoAlertService:
    def create(self, incident):
        return {"status": "DEMO ALERT CREATED", "mode": "SIMULATED — no external dispatch",
                "incident_id": incident["incident_id"], "created_at": datetime.now(timezone.utc).isoformat()}


class IncidentStore:
    """SQLite archive. Media BLOBs are written atomically with final metadata."""
    def __init__(self, root=None, config=SAFETY):
        self.root = Path(root or ROOT / "outputs/incidents")
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / "incidents.sqlite"
        self.max_blob_bytes = config.incident_blob_max_bytes
        self.retention_days = config.incident_retention_days
        self.max_records = config.incident_max_records
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS incidents (id TEXT PRIMARY KEY, created_at TEXT, payload TEXT)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(incidents)")}
            additions = {
                "analysis_id": "TEXT", "event_type": "TEXT", "verification_status": "TEXT",
                "event_time": "REAL", "clip": "BLOB", "clip_mime": "TEXT", "clip_bytes": "INTEGER",
                "screenshot": "BLOB", "screenshot_mime": "TEXT", "screenshot_bytes": "INTEGER",
                "expires_at": "TEXT",
            }
            for name, kind in additions.items():
                if name not in columns:
                    db.execute(f"ALTER TABLE incidents ADD COLUMN {name} {kind}")
            db.execute("CREATE INDEX IF NOT EXISTS incidents_analysis ON incidents(analysis_id,created_at)")
            db.execute("CREATE INDEX IF NOT EXISTS incidents_filters ON incidents(event_type,verification_status,created_at)")
            db.execute("""UPDATE incidents SET payload=json_set(payload, '$.evidence_status', 'CAPTURE INTERRUPTED')
                        WHERE json_extract(payload, '$.evidence_status')='CAPTURING AFTER EVENT'
                        AND created_at < datetime('now', '-15 minutes')""")
        self.purge()

    def _connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def next_id(self):
        """Allocate a human-readable daily sequence while holding SQLite's write lock."""
        prefix = "CZ-" + datetime.now(timezone.utc).strftime("%Y%m%d") + "-"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            count = db.execute("SELECT COUNT(*) FROM incidents WHERE id LIKE ?", (prefix + "%",)).fetchone()[0]
            return f"{prefix}{count + 1:03d}"

    @staticmethod
    def _columns(record):
        return (record.get("analysis_id"), record.get("event_type"), record.get("verification_status"),
                record.get("timestamp"), record.get("expires_at"))

    def save(self, record, clip_bytes=None, screenshot_bytes=None):
        """Upsert metadata and optional BLOBs in one transaction."""
        if clip_bytes is not None and len(clip_bytes) > self.max_blob_bytes:
            raise ValueError(f"incident clip exceeds {self.max_blob_bytes} byte SQLite limit")
        if screenshot_bytes is not None and len(screenshot_bytes) > self.max_blob_bytes:
            raise ValueError("incident screenshot exceeds SQLite size limit")
        analysis_id, event_type, status, event_time, expires_at = self._columns(record)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("""
                INSERT INTO incidents
                (id,created_at,payload,analysis_id,event_type,verification_status,event_time,clip,clip_mime,clip_bytes,
                 screenshot,screenshot_mime,screenshot_bytes,expires_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                  created_at=excluded.created_at, payload=excluded.payload, analysis_id=excluded.analysis_id,
                  event_type=excluded.event_type, verification_status=excluded.verification_status,
                  event_time=excluded.event_time, expires_at=excluded.expires_at,
                  clip=COALESCE(excluded.clip,incidents.clip), clip_mime=COALESCE(excluded.clip_mime,incidents.clip_mime),
                  clip_bytes=COALESCE(excluded.clip_bytes,incidents.clip_bytes),
                  screenshot=COALESCE(excluded.screenshot,incidents.screenshot),
                  screenshot_mime=COALESCE(excluded.screenshot_mime,incidents.screenshot_mime),
                  screenshot_bytes=COALESCE(excluded.screenshot_bytes,incidents.screenshot_bytes)
                """, (record["incident_id"], record["created_at"], json.dumps(record), analysis_id, event_type, status,
                      event_time, clip_bytes, "video/mp4" if clip_bytes else None, len(clip_bytes) if clip_bytes else None,
                      screenshot_bytes, "image/jpeg" if screenshot_bytes else None,
                      len(screenshot_bytes) if screenshot_bytes else None, expires_at))

    def is_duplicate(self, event, analysis_id):
        """Only de-duplicate candidates in one run; replaying a file remains testable."""
        t, cooldown = event.get("timestamp", 0), event.get("cooldown_seconds", SAFETY.cooldown_seconds)
        with self._connect() as db:
            row = db.execute("""SELECT id FROM incidents WHERE analysis_id IS ? AND event_time BETWEEN ? AND ?
                              ORDER BY ABS(event_time-?) LIMIT 1""",
                             (analysis_id, t - cooldown, t + cooldown, t)).fetchone()
        return row["id"] if row else None

    def list(self, analysis_id=None, start_date=None, end_date=None, event_types=None, statuses=None):
        clauses, args = [], []
        if analysis_id is not None:
            clauses.append("analysis_id=?"); args.append(analysis_id)
        if start_date:
            clauses.append("created_at>=?"); args.append(str(start_date))
        if end_date:
            clauses.append("created_at<?"); args.append(str(end_date) + "T23:59:59.999999+00:00")
        if event_types:
            clauses.append("event_type IN (" + ",".join("?" * len(event_types)) + ")"); args.extend(event_types)
        if statuses:
            clauses.append("verification_status IN (" + ",".join("?" * len(statuses)) + ")"); args.extend(statuses)
        query = "SELECT payload,clip_bytes,screenshot_bytes FROM incidents"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT 200"
        with self._connect() as db:
            rows = db.execute(query, args).fetchall()
        result = []
        for row in rows:
            record = json.loads(row["payload"])
            if row["clip_bytes"]:
                record["clip_bytes"] = row["clip_bytes"]
            if row["screenshot_bytes"]:
                record["screenshot_bytes"] = row["screenshot_bytes"]
            result.append(record)
        return result

    def get_clip(self, incident_id):
        with self._connect() as db:
            row = db.execute("SELECT clip FROM incidents WHERE id=?", (incident_id,)).fetchone()
        return row["clip"] if row and row["clip"] else None

    def get_screenshot(self, incident_id):
        with self._connect() as db:
            row = db.execute("SELECT screenshot FROM incidents WHERE id=?", (incident_id,)).fetchone()
        return row["screenshot"] if row and row["screenshot"] else None

    def purge(self):
        if self.retention_days < 0:
            return
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.retention_days)).isoformat()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            expired = db.execute("SELECT id FROM incidents WHERE created_at < ?", (cutoff,)).fetchall()
            overflow = db.execute("SELECT id FROM incidents ORDER BY created_at DESC LIMIT -1 OFFSET ?",
                                  (self.max_records,)).fetchall() if self.max_records else []
            victims = {row["id"] for row in [*expired, *overflow]}
            if victims:
                db.executemany("DELETE FROM incidents WHERE id=?", [(key,) for key in victims])
        for incident_id in victims:
            folder = (self.root / incident_id).resolve()
            if folder.parent == self.root.resolve():
                shutil.rmtree(folder, ignore_errors=True)


class EvidenceBuffer:
    """Timestamped JPEG ring; encoding occurs after monitoring has continued."""
    def __init__(self, camera, store=None, config=SAFETY, source_kind="video", started_at=None,
                 analysis_id=None, source_id=None, source_name=None, media_digest=None):
        self.media_digest = media_digest
        self.analysis_id, self.source_id, self.source_name = analysis_id, source_id, source_name
        self.cfg, self.camera, self.store = config, camera, store or IncidentStore(config=config)
        self.feature_history, self.frames, self.pending = deque(), deque(), []
        self.last_t, self.last_error = -1.0, None
        self.source_kind, self.started_at = source_kind, started_at or datetime.now(timezone.utc)
        self.encoder = ThreadPoolExecutor(max_workers=1, thread_name_prefix="CrashZero-evidence")
        self.exports = []

    def add(self, t, frame, features=None):
        if features is not None:
            self.feature_history.append({"timestamp": t, **features})
            while self.feature_history and t - self.feature_history[0]["timestamp"] > self.cfg.before_seconds + self.cfg.verification_seconds + 1:
                self.feature_history.popleft()
            for pending in self.pending:
                pending["features"].append({"timestamp": t, **features})
        if t - self.last_t < 1 / self.cfg.buffer_fps - .001:
            return
        ok, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 78])
        if not ok:
            return
        entry = (t, jpg.tobytes()); self.last_t = t; self.frames.append(entry)
        while self.frames and t - self.frames[0][0] > self.cfg.before_seconds + self.cfg.verification_seconds + 1:
            self.frames.popleft()
        for pending in self.pending:
            if t > pending["frames"][-1][0]:
                pending["frames"].append(entry)
        for pending in list(self.pending):
            if t >= pending["record"]["timestamp"] + self.cfg.after_seconds:
                self._finish(pending, False)

    def _annotated_screenshot(self, jpg, incident_id, timestamp):
        image = cv2.imdecode(np.frombuffer(jpg, np.uint8), cv2.IMREAD_COLOR)
        cv2.putText(image, f"{incident_id}  t={timestamp:.3f}s", (12, 28), cv2.FONT_HERSHEY_SIMPLEX,
                    .65, (20, 20, 235), 2, cv2.LINE_AA)
        ok, output = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 88])
        return output.tobytes() if ok else jpg

    def trigger(self, event):
        if not self.frames or self.store.is_duplicate(event, self.analysis_id):
            return None
        incident_id = self.store.next_id()
        folder = self.store.root / incident_id
        folder.mkdir(parents=True, exist_ok=False)
        frames = [f for f in self.frames if f[0] >= event["timestamp"] - self.cfg.before_seconds]
        if not frames:
            frames = [self.frames[-1]]
        event_frame = min(frames, key=lambda f: abs(f[0] - event["timestamp"]))
        screenshot = self._annotated_screenshot(event_frame[1], incident_id, event["timestamp"])
        (folder / "event.jpg").write_bytes(screenshot)
        (folder / "before.jpg").write_bytes(frames[0][1])
        now = datetime.now(timezone.utc)
        record = {**event, **self.camera.metadata(), "incident_id": incident_id, "incident_name": f"{event['state'].title()} · {self.camera.name}",
                  "created_at": now.isoformat(), "event_type": event["state"], "verification_status": event["state"],
                  "media_digest": self.media_digest, "analysis_id": self.analysis_id, "source_id": self.source_id,
                  "source_name": self.source_name, "camera_name": self.camera.name, "registered_location": self.camera.location,
                  "source_kind": self.source_kind, "time_basis": "source offset in seconds" if self.source_kind != "live camera" else "capture clock",
                  "observed_at": (self.started_at + timedelta(seconds=event["timestamp"])).isoformat() if self.source_kind == "live camera" else None,
                  "screenshot_path": str(folder / "event.jpg"), "before_path": str(folder / "before.jpg"),
                  "video_clip_path": None, "evidence_status": "CAPTURING AFTER EVENT",
                  "expires_at": (now + timedelta(days=self.store.retention_days)).isoformat() if self.store.retention_days >= 0 else None}
        record["alert"] = DemoAlertService().create(record); record["alert_status"] = record["alert"]["status"]
        try:
            self.store.save(record, screenshot_bytes=screenshot)
        except (OSError, sqlite3.Error, ValueError) as exc:
            self.last_error = f"incident candidate was not saved: {exc}"
            shutil.rmtree(folder, ignore_errors=True)
            return None
        self.pending.append({"record": record, "folder": folder, "frames": frames,
                             "features": list(self.feature_history), "screenshot": screenshot})
        return incident_id

    def _finish(self, pending, truncated):
        self.pending.remove(pending)
        self.exports.append(self.encoder.submit(self._encode, pending, truncated))

    def _encode(self, pending, truncated):
        record, folder, frames = pending["record"], pending["folder"], pending["frames"]
        try:
            (folder / "features.json").write_text(json.dumps(pending["features"], indent=2))
            record["features_path"] = str(folder / "features.json")
            (folder / "after.jpg").write_bytes(frames[-1][1]); record["after_path"] = str(folder / "after.jpg")
            record.update({"clip_start": frames[0][0], "clip_end": frames[-1][0],
                           "frame_timestamps": [round(t, 6) for t, _ in frames],
                           "pre_event_truncated": frames[0][0] > record["timestamp"] - self.cfg.before_seconds + .2,
                           "post_event_truncated": truncated or frames[-1][0] < record["timestamp"] + self.cfg.after_seconds - .2})
            frame = cv2.imdecode(np.frombuffer(frames[0][1], np.uint8), cv2.IMREAD_COLOR)
            height, width = frame.shape[:2]
            raw = folder / "_raw.mp4"
            writer = cv2.VideoWriter(str(raw), cv2.VideoWriter_fourcc(*"mp4v"), self.cfg.buffer_fps, (width, height))
            if not writer.isOpened():
                raise RuntimeError("MP4 encoder unavailable")
            try:
                index = 0
                for sample_t in np.arange(frames[0][0], frames[-1][0] + .05, 1 / self.cfg.buffer_fps):
                    while index + 1 < len(frames) and frames[index + 1][0] <= sample_t:
                        index += 1
                    writer.write(cv2.imdecode(np.frombuffer(frames[index][1], np.uint8), cv2.IMREAD_COLOR))
            finally:
                writer.release()
            output = folder / f"{record['incident_id']}.mp4"
            codec = "mp4v fallback"
            try:
                import imageio_ffmpeg
                subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-y", "-i", str(raw), "-an", "-c:v", "libx264",
                                "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)], check=True, timeout=30, capture_output=True)
                raw.unlink(missing_ok=True); codec = "h264"
            except Exception:
                shutil.move(str(raw), str(output))
            clip = output.read_bytes()
            record.update({"video_clip_path": str(output), "clip_codec": codec, "evidence_status": "EVIDENCE SAVED"})
            self.store.save(record, clip_bytes=clip, screenshot_bytes=pending["screenshot"])
            from src.alerts.service import AlertService
            import os
            root = self.store.root / "calls" if os.getenv("CRASHZERO_V2_HOSTED") == "1" else ROOT / "outputs/calls"
            AlertService(root).automatic(record)
        except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
            self.last_error = f"incident evidence save failed: {exc}"
            record["evidence_status"] = "SCREENSHOTS SAVED — CLIP ENCODING OR DATABASE FAILED"
            try:
                self.store.save(record, screenshot_bytes=pending["screenshot"])
            except (OSError, sqlite3.Error, ValueError):
                pass

    def close(self):
        for pending in list(self.pending):
            self._finish(pending, True)
        self.encoder.shutdown(wait=True)
        for future in self.exports:
            future.result()
