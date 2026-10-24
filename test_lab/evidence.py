"""Extract exactly two JPEG frames using source frame indices and FPS."""
from pathlib import Path
import math
import cv2


def save_frame_pair(frames, folder, max_width=1024, quality=75):
    """Persist exactly two timestamped BGR frames from a running source."""
    if len(frames) != 2:
        raise ValueError('Exactly two evidence frames are required.')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths, timestamps = [], []
    for number, (timestamp, frame) in enumerate(frames, 1):
        if frame is None:
            raise ValueError('An evidence frame is unavailable.')
        if frame.shape[1] > max_width:
            width = max_width
            height = round(frame.shape[0] * width / frame.shape[1])
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        destination = folder / f'frame_{number}.jpg'
        if not cv2.imwrite(str(destination), frame, [cv2.IMWRITE_JPEG_QUALITY, quality]):
            raise ValueError('Could not save evidence frame.')
        paths.append(str(destination))
        timestamps.append(float(timestamp))
    return paths, timestamps


def capture_pair(path, folder, event_timestamp, max_width=1024, quality=75):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(path))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    if not cap.isOpened() or not math.isfinite(fps) or fps <= 0:
        cap.release()
        raise ValueError('Unable to extract evidence from this video.')
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    first_index = max(0, round(event_timestamp * fps))
    if total > 0:
        first_index = min(first_index, total - 1)
    target_indices = [first_index, first_index + round(fps)]
    if total > 0:
        target_indices[1] = min(target_indices[1], total - 1)
    paths, timestamps = [], []
    limitation = None
    for number, target in enumerate(target_indices, 1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        ok, frame = cap.read()
        actual_index = target
        if not ok and number == 2 and total > 0:
            actual_index = total - 1
            cap.set(cv2.CAP_PROP_POS_FRAMES, actual_index)
            ok, frame = cap.read()
        if not ok:
            cap.release()
            raise ValueError('Could not decode both evidence frames.')
        if frame.shape[1] > max_width:
            width = max_width
            height = round(frame.shape[0] * width / frame.shape[1])
            frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
        destination = folder / f'frame_{number}.jpg'
        if not cv2.imwrite(str(destination), frame, [cv2.IMWRITE_JPEG_QUALITY, quality]):
            cap.release()
            raise ValueError('Could not save evidence frame.')
        paths.append(str(destination))
        timestamps.append(actual_index / fps)
    cap.release()
    if timestamps[1] - timestamps[0] < .8:
        limitation = 'Video ended before a frame one second later; the final available frame was used.'
    return paths, timestamps, limitation
