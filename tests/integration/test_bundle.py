"""
Integration tests for the Landscape scalable bundle, using Postgres, RabbitMQ,
and HAProxy.
"""

import jubilant
import requests

from tests.helpers import build_url


def _get_haproxy_address(juju: jubilant.Juju) -> str:
    """
    Get the public address for the HAProxy unit in the Juju model.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address
    assert host, "No public address on haproxy/0 unit"
    return host


def test_metrics_forbidden(juju: jubilant.Juju, bundle: None):
    """
    Requests to `/metrics` are denied with a 403.

    This includes the older `<host>/metrics` endpoint, and any newer per-service
    endpoints that end with `/metrics`, like `<host>/api/metrics`.
    """
    host = _get_haproxy_address(juju)

    response = requests.get(build_url("http", host, "/metrics"))
    assert response.status_code == 403

    response = requests.get(build_url("https", host, "/metrics"), verify=False)
    assert response.status_code == 403

    services = ("message-system", "api", "ping")

    for service in services:
        for scheme in ("http", "https"):
            url = build_url(scheme, host, f"/{service}/metrics")
            assert requests.get(url, verify=False).status_code == 403


def test_pingserver_routing(juju: jubilant.Juju, bundle: None):
    """
    HAProxy correctly routes pingserver requests to the pingserver backend.

    Pingserver runs over HTTPS and HTTP.
    """
    host = _get_haproxy_address(juju)

    for scheme in ("http", "https"):
        url = build_url(scheme, host, "/ping")
        assert requests.get(url, verify=False, allow_redirects=False).status_code == 200


def test_message_server_routing(juju: jubilant.Juju, bundle: None):
    """
    HAProxy correctly routes message system requests to the message server backend.

    Message server runs only on HTTPS by default. HAProxy returns a 302 for HTTP
    requests.
    """
    host = _get_haproxy_address(juju)

    response = requests.get(build_url("https", host, "/message-system"), verify=False)
    assert response.status_code == 200

    response = requests.get(
        build_url("http", host, "/message-system"),
        allow_redirects=False,
    )
    assert response.status_code == 302


def test_api_routing(juju: jubilant.Juju, bundle: None):
    """
    HAProxy correctly routes API requests to the API backend.

    The API runs only on HTTPS by default. HAProxy returns a 302 for HTTP requests.

    NOTE: the API does not have a `/` route to use as a simple check; use the `/about`
    endpoint as a stand-in for a health endpoint.
    """
    host = _get_haproxy_address(juju)

    response = requests.get(build_url("https", host, "/api/about"), verify=False)
    assert response.status_code == 200

    response = requests.get(
        build_url("http", host, "/api/about"),
        allow_redirects=False,
    )
    assert response.status_code == 302
