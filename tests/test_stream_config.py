import pytest
from src.video.stream_config import validate_stream_url


@pytest.mark.parametrize('url', [
    'rtsp://192.168.1.20:554/live', 'http://camera.local/video',
    'rtsp://user:p%40ss@10.0.0.2:8554/main',
])
def test_local_camera_addresses(url):
    assert validate_stream_url(url) == url


@pytest.mark.parametrize('url', [
    'rtsp://127.0.0.1/live', 'rtsp://192.168.1.20/live',
    'rtsp://169.254.169.254/live', 'rtsp://10.0.0.2/live',
    'rtsp://[::1]/live', 'rtsp://[::ffff:8.8.8.8]/live',
    'rtsp://224.0.0.1/live', 'rtsp://camera.local/live',
    'https://8.8.8.8/playlist.m3u8',
])
def test_cloud_rejects_non_public_camera_endpoints(url):
    with pytest.raises(ValueError):
        validate_stream_url(url, hosted=True)


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'rtsp://', 'rtsp://host:bad/live', '192.168.1.20', 'rtsp://host:0/live'])
def test_invalid_camera_urls(url):
    with pytest.raises(ValueError):
        validate_stream_url(url)


def test_cloud_public_ip_and_errors_do_not_disclose_credentials():
    url = 'rtsp://operator:secret@8.8.8.8:554/main'
    assert validate_stream_url(url, hosted=True) == url
    with pytest.raises(ValueError) as error:
        validate_stream_url('rtsp://operator:secret@192.168.1.20:bad/main', hosted=True)
    assert 'secret' not in str(error.value)


def test_stream_backend_has_timeouts_and_releases_failed_connection(monkeypatch):
    import cv2
    from src.video.source import StreamSource
    calls = []
    class Unavailable:
        released = False
        def isOpened(self): return False
        def release(self): self.released = True
    capture = Unavailable()
    def open_capture(*args):
        calls.append(args)
        return capture
    monkeypatch.setattr(cv2, 'VideoCapture', open_capture)
    with pytest.raises(ValueError, match='Stream unavailable'):
        StreamSource('rtsp://192.168.1.20/live').open()
    assert calls[0][1] == cv2.CAP_FFMPEG
    assert calls[0][2] == [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000, cv2.CAP_PROP_READ_TIMEOUT_MSEC, 3000]
    assert capture.released
