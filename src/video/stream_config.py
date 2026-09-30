"""Validate camera endpoints without including credentials in errors or metadata."""
import ipaddress
from urllib.parse import urlsplit


def validate_stream_url(value, *, hosted=False):
    url = value.strip()
    try:
        parts = urlsplit(url)
        port = parts.port
        if not parts.hostname or port == 0 or any(c.isspace() for c in url):
            raise ValueError
    except ValueError:
        raise ValueError('Enter a complete camera stream URL with a valid host and port.') from None
    if parts.scheme not in ('rtsp', 'rtsps', 'http', 'https') or parts.fragment:
        raise ValueError('Use an RTSP, RTSPS, HTTP or HTTPS video stream URL.')
    if hosted:
        # A public app must not turn arbitrary inputs into access to host-internal
        # services. Literal global IPs also avoid DNS rebinding; RTSP excludes
        # HTTP redirects and HLS playlists that can reference internal resources.
        if parts.scheme not in ('rtsp', 'rtsps'):
            raise ValueError('Cloud cameras require RTSP or RTSPS. Use the local app for HTTP camera streams.')
        try:
            address = ipaddress.ip_address(parts.hostname)
        except ValueError:
            raise ValueError('For cloud analysis, use the camera gateway’s public IP address, not a hostname.') from None
        mapped = isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None
        if not address.is_global or address.is_multicast or mapped:
            raise ValueError('This address is not reachable as a public camera. Run CrashZero on the camera’s network for private IP cameras.')
    return url
