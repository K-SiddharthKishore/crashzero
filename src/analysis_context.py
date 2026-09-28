"""Stable source identities for selection; analysis IDs identify individual runs."""
import hashlib
from pathlib import Path


def file_selection(path, name):
    identity = hashlib.sha256(str(Path(path).resolve()).encode()).hexdigest()
    return {'id': 'file:' + identity, 'name': name}


def camera_selection(camera_id, kind, index=None):
    # Never use credential-bearing stream URLs in saved selection metadata.
    return {'id': f'camera:{camera_id}:{kind}:{index}', 'name': camera_id}
