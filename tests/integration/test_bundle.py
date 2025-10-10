"""
Integration tests for the Landscape scalable bundle, using Postgres, RabbitMQ,
and HAProxy.

NOTE: These tests assume an IPv4 public address for HAProxy. Our HAProxy relation
does not currently bind to IPv6.
"""

import jubilant
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry


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


def test_redirect_https_all(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=all`, then redirect all HTTP requests on all routes to HTTPS.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address
    juju.config("landscape-server", values={"redirect_https": "all"})
    juju.wait(jubilant.all_active, timeout=10.0)

    redirect_routes = (
        "",
        "api/about",
        "attachment",
        "hashid-databases",
        "ping",
        "message-system",
        "repository",
        "upload",
        "zzz-some-default-route",
    )

    for route in redirect_routes:

        assert requests.get(
            f"http://{host}/{route}",
            allow_redirects=False,
        ).is_redirect


def test_redirect_https_none(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=none`, then do not redirect any HTTP requests on any routes
    to HTTPS.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address
    juju.config("landscape-server", values={"redirect_https": "none"})
    juju.wait(jubilant.all_active, timeout=10.0)

    no_redirect_routes = (
        "",
        "api/about",
        "attachment",
        "hashid-databases",
        "ping",
        "message-system",
        "repository",
        "upload",
        "zzz-some-default-route",
    )

    for route in no_redirect_routes:

        assert not requests.get(
            f"http://{host}/{route}",
            allow_redirects=False,
        ).is_redirect


def test_redirect_https_default(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=default`, then redirect all HTTP requests except for those to the
    /repository and /ping routes to HTTPS.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address
    juju.config("landscape-server", values={"redirect_https": "default"})
    juju.wait(jubilant.all_active, timeout=10.0)

    no_redirect_routes = (
        "ping",
        "repository",
    )
    for route in no_redirect_routes:

        assert not requests.get(
            f"http://{host}/{route}",
            allow_redirects=False,
        ).is_redirect

    redirect_routes = (
        "",
        "api/about",
        "attachment",
        "hashid-databases",
        "message-system",
        "upload",
        "zzz-some-default-route",
    )
    for route in redirect_routes:

        assert requests.get(
            f"http://{host}/{route}",
            allow_redirects=False,
        ).is_redirect


@pytest.mark.parametrize("route", ["ping", "api/about", "message-system", ""])
def test_services_up_over_https(juju: jubilant.Juju, bundle: None, route: str):
    """
    Services are responding over HTTPS.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address

    response = get_session().get(f"https://{host}/{route}", verify=False)
    assert response.status_code == 200


def get_session(
    retries: int = 5,
    backoff_factor: float = 0.3,
    status_forcelist: tuple[int, ...] = (503,),
) -> requests.Session:
    """
    Create a session that includes retries for 503 statuses.

    This is useful for HAProxy tests because the HAProxy unit and the Landscape unit
    can report "ready" in Juju even if Landscape server is not yet ready to serve
    requests.
    """

    session = requests.Session()
    strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"),
        raise_on_status=True,
    )

    adapter = HTTPAdapter(max_retries=strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
