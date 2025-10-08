"""
Integration tests for the Landscape scalable bundle, using Postgres, RabbitMQ,
and HAProxy.

NOTE: These tests assume an IPv4 public address for HAProxy. Our HAProxy relation
does not currently bind to IPv6.
"""

import jubilant
import requests


def test_metrics_forbidden(juju: jubilant.Juju, bundle: None):
    """
    Requests to `/metrics` are denied with a 403.

    This includes the older `<host>/metrics` endpoint, and any newer per-service
    endpoints that end with `/metrics`, like `<host>/api/metrics`.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address

    assert requests.get(f"http://{host}/metrics").status_code == 403
    assert requests.get(f"https://{host}/metrics", verify=False).status_code == 403

    services = ("message-system", "api", "ping")

    for service in services:
        for scheme in ("http", "https"):
            url = f"{scheme}://{host}/{service}/metrics"
            assert requests.get(url, verify=False).status_code == 403


def test_pingserver_routing(juju: jubilant.Juju, bundle: None):
    """
    HAProxy correctly routes pingserver requests to the pingserver backend.

    Pingserver runs over HTTPS and HTTP.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address

    for scheme in ("http", "https"):
        url = f"{scheme}://{host}/ping"
        assert requests.get(url, verify=False, allow_redirects=False).status_code == 200


def test_message_server_routing(juju: jubilant.Juju, bundle: None):
    """
    HAProxy correctly routes message system requests to the message server backend.

    Message server runs only on HTTPS by default. HAProxy returns a 302 for HTTP
    requests.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address

    response = requests.get(f"https://{host}/message-system", verify=False)
    assert response.status_code == 200

    response = requests.get(
        f"http://{host}/message-system",
        verify=False,
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
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address

    response = requests.get(f"https://{host}/api/about", verify=False)
    assert response.status_code == 200

    response = requests.get(
        f"http://{host}/api/about",
        verify=False,
        allow_redirects=False,
    )
    assert response.status_code == 302
