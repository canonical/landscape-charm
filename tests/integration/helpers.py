"""
Helper functions for integration tests.
"""

import ipaddress
from urllib.parse import urlunparse


def build_url(scheme: str, host: str, port: int | None = None, path: str = "") -> str:
    """
    Build a URL, including consideration for an IPv6 host that must be wrapped in
    brackets.
    """
    try:
        ip = ipaddress.ip_address(host)
        if ip.version == 6:
            host = f"[{host}]"
    except ValueError:
        pass  # don't modify hostnames

    netloc = f"{host}:{port}" if port else host

    return urlunparse((scheme, netloc, path, "", "", ""))
