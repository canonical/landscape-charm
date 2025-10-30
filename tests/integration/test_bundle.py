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
    juju.wait(jubilant.all_active, timeout=30.0)

    redirect_routes = (
        "about",
        "api/about",
        "attachment",
        "hashid-databases",
        "ping",
        "message-system",
        "repository",
        "upload",
        "zzz-some-default-route",
    )

    session = get_session()
    for route in redirect_routes:
        url = f"http://{host}/{route}"
        response = session.get(url, allow_redirects=False)
        assert response.is_redirect, f"Got {response} from {url}"


def test_redirect_https_none(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=none`, then do not redirect any HTTP requests on any routes
    to HTTPS.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address
    juju.config("landscape-server", values={"redirect_https": "none"})
    juju.wait(jubilant.all_active, timeout=30.0)

    no_redirect_routes = (
        "about",
        "api/about",
        "attachment",
        "hashid-databases",
        "ping",
        "message-system",
        "repository",
        "upload",
        "zzz-some-default-route",
    )

    session = get_session()
    for route in no_redirect_routes:
        url = f"http://{host}/{route}"
        response = session.get(url, allow_redirects=False)
        assert not response.is_redirect, f"Got {response} from {url}"


def test_redirect_https_default(juju: jubilant.Juju, bundle: None):
    """
    If `redirect_https=default`, then redirect all HTTP requests except for those to the
    /repository and /ping routes to HTTPS.
    """
    host = juju.status().apps["haproxy"].units["haproxy/0"].public_address
    juju.config("landscape-server", values={"redirect_https": "default"})
    juju.wait(jubilant.all_active, timeout=30.0)

    no_redirect_routes = (
        "ping",
        "repository",
    )

    session = get_session()
    for route in no_redirect_routes:
        url = f"http://{host}/{route}"
        response = session.get(url, allow_redirects=False)
        assert not response.is_redirect, f"Got {response} from {url}"

    redirect_routes = (
        "about",
        "api/about",
        "attachment",
        "hashid-databases",
        "message-system",
        "upload",
        "zzz-some-default-route",
    )
    for route in redirect_routes:
        url = f"http://{host}/{route}"
        response = session.get(url, allow_redirects=False)
        assert response.is_redirect, f"Got {response} from {url}"


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

    Copied from https://urllib3.readthedocs.io/en/stable/reference/urllib3.util.html

    `retries`:
        Total number of retries to allow. Takes precedence over other counts.
        Set to None to remove this constraint and fall back on other counts.
        Set to 0 to fail on the first retry.

    `backoff_factor`:
        A backoff factor to apply between attempts after the second try (most errors
        are resolved immediately by a second try without a delay). urllib3 will sleep
        for: {backoff factor} * (2 ** ({number of previous retries})) seconds.

    `status_forcelist`:
        A set of integer HTTP status codes that we should force a retry on. A retry is
        initiated if the request method is in allowed_methods and the response status
        code is in status_forcelist. By default, this is disabled with None.

    """

    session = requests.Session()
    strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _supports_legacy_pgsql(juju: jubilant.Juju) -> bool:
    app = juju.status().apps["postgresql"]
    return "db-admin" in getattr(app, "relations", {})


def test_prefers_modern_database_relation(juju: jubilant.Juju, bundle: None):
    status = juju.status()
    initial_relations = set(status.apps["landscape-server"].relations)

    if "database" not in initial_relations:
        juju.integrate("landscape-server:database", "postgresql:database")
    if _supports_legacy_pgsql(juju) and "db" not in initial_relations:
        juju.integrate("landscape-server:db", "postgresql:db-admin")

    juju.wait(jubilant.all_active, timeout=120)
    relations = set(juju.status().apps["landscape-server"].relations)

    assert "database" in relations
    if _supports_legacy_pgsql(juju):
        assert "db" in relations
    else:
        assert "db" not in relations

    _restore_relations(juju, initial_relations)


def test_falls_back_to_legacy_relation(juju: jubilant.Juju, bundle: None):
    if not _supports_legacy_pgsql(juju):
        pytest.skip("Legacy pgsql relation not available on this PostgreSQL charm")

    status = juju.status()
    initial_relations = set(status.apps["landscape-server"].relations)

    if "database" in initial_relations:
        juju.remove_relation("landscape-server:database", "postgresql:database")
    if "db" not in initial_relations:
        juju.integrate("landscape-server:db", "postgresql:db-admin")

    juju.wait(jubilant.all_active, timeout=120)
    relations = set(juju.status().apps["landscape-server"].relations)

    assert "db" in relations

    _restore_relations(juju, initial_relations)


def _restore_relations(juju: jubilant.Juju, expected: set[str]) -> None:
    relations = set(juju.status().apps["landscape-server"].relations)

    if "database" in expected and "database" not in relations:
        juju.integrate("landscape-server:database", "postgresql:database")
    if "database" not in expected and "database" in relations:
        juju.remove_relation("landscape-server", "postgresql")

    relations = set(juju.status().apps["landscape-server"].relations)

    if _supports_legacy_pgsql(juju):
        if "db" in expected and "db" not in relations:
            juju.integrate("landscape-server:db", "postgresql:db-admin")
        if "db" not in expected and "db" in relations:
            juju.remove_relation("landscape-server:db", "postgresql:db-admin")
