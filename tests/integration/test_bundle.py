"""
Integration tests for the Landscape scalable bundle, using Postgres, RabbitMQ,
and Landscape Server.

NOTE: These tests assume an IPv4 public address for the Landscape Server charm.
"""

import json
import time

import jubilant
import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

from charm import DEFAULT_SERVICES, LANDSCAPE_UBUNTU_INSTALLER_ATTACH, LEADER_SERVICES
import haproxy


def test_metrics_forbidden(juju: jubilant.Juju, bundle: None):
    """
    Requests to `/metrics` are denied with a 403.

    This includes the older `<host>/metrics` endpoint, and any newer per-service
    endpoints that end with `/metrics`, like `<host>/api/metrics`.
    """
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )

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
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )
    juju.config("landscape-server", values={"redirect_https": "all"})
    juju.wait(jubilant.all_active, timeout=300)

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
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )
    juju.config("landscape-server", values={"redirect_https": "none"})
    juju.wait(jubilant.all_active, timeout=300)

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
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )
    juju.config("landscape-server", values={"redirect_https": "default"})
    juju.wait(jubilant.all_active, timeout=300)

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
    host = (
        juju.status()
        .apps["landscape-server"]
        .units["landscape-server/0"]
        .public_address
    )

    response = get_session().get(f"https://{host}/{route}", verify=False)
    assert response.status_code == 200


def get_session(
    retries: int = 5,
    backoff_factor: float = 0.3,
    status_forcelist: tuple[int, ...] = (503,),
) -> requests.Session:
    """
    Create a session that includes retries for 503 statuses.

    This is useful for load balancing tests because the Landscape unit
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


def _has_legacy_pg(juju: jubilant.Juju) -> bool:
    pg = juju.status().apps["postgresql"]
    return "db-admin" in pg.relations


def _has_modern_pg(juju: jubilant.Juju) -> bool:
    pg = juju.status().apps["postgresql"]
    return "database" in pg.relations


def _supports_legacy_pg(juju: jubilant.Juju) -> bool:
    pg = juju.status().apps["postgresql"]
    # '14/x' and 'latest/x' tracks support legacy
    return "14" in pg.charm_channel or "latest" in pg.charm_channel


def _restore_db_relations(juju: jubilant.Juju, expected: set[str]) -> None:
    relations = set(juju.status().apps["landscape-server"].relations)

    # Used to have modern, needs it back
    if "database" in expected and "database" not in relations:
        # Will error if both are integrated at the same time
        if "db" in relations:
            juju.remove_relation(
                "landscape-server:db", "postgresql:db-admin", force=True
            )
            juju.wait(lambda status: not _has_legacy_pg(juju), timeout=120)

        juju.integrate("landscape-server:database", "postgresql:database")

    elif "database" not in expected and "database" in relations:
        juju.remove_relation(
            "landscape-server:database", "postgresql:database", force=True
        )
        juju.wait(lambda status: not _has_modern_pg(juju), timeout=120)

    # Refresh after they might have changed
    relations = set(juju.status().apps["landscape-server"].relations)

    # Supports for legacy was dropped in PG 16+
    if _supports_legacy_pg(juju):
        # Used to have legacy, needs it back
        if "db" in expected and "db" not in relations:
            # Will error if both are integrated at the same time
            if "database" in relations:
                juju.remove_relation(
                    "landscape-server:database", "postgresql:database", force=True
                )
                juju.wait(lambda status: not _has_modern_pg(juju), timeout=120)

            juju.integrate("landscape-server:db", "postgresql:db-admin")

        elif "db" not in expected and "db" in relations:
            juju.remove_relation(
                "landscape-server:db", "postgresql:db-admin", force=True
            )
            juju.wait(lambda status: not _has_legacy_pg(juju), timeout=120)


def test_modern_database_relation(juju: jubilant.Juju, bundle: None):
    """
    Test the modern `database` interface.
    """
    status = juju.status()
    initial_relations = set(status.apps["landscape-server"].relations)

    if "db" in initial_relations:
        juju.remove_relation("landscape-server:db", "postgresql:db-admin", force=True)
        juju.wait(lambda status: not _has_legacy_pg(juju), timeout=120)

        juju.integrate("landscape-server:database", "postgresql:database")

    elif "database" not in initial_relations:
        juju.integrate("landscape-server:database", "postgresql:database")
        juju.wait(lambda status: _has_modern_pg(juju), timeout=120)

    relations = set(juju.status().apps["landscape-server"].relations)

    assert "database" in relations

    _restore_db_relations(juju, initial_relations)


def test_legacy_db_relation(juju: jubilant.Juju, bundle: None):
    """
    Test the legacy `db` interface.
    """
    if not _supports_legacy_pg(juju):
        pytest.skip("Legacy pgsql relation not available on this PostgreSQL charm")

    status = juju.status()
    initial_relations = set(status.apps["landscape-server"].relations)

    if "database" in initial_relations:
        juju.remove_relation(
            "landscape-server:database", "postgresql:database", force=True
        )
        juju.wait(lambda status: not _has_modern_pg(juju), timeout=120)
        juju.integrate("landscape-server:db", "postgresql:db-admin")

    elif "db" not in initial_relations:
        juju.integrate("landscape-server:db", "postgresql:db-admin")
        juju.wait(lambda status: _has_legacy_pg(juju), timeout=120)

    relations = set(juju.status().apps["landscape-server"].relations)

    assert "db" in relations

    _restore_db_relations(juju, initial_relations)


def test_all_services_up(juju: jubilant.Juju, bundle: None):
    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units
    config = juju.config("landscape-server")
    enable_ubuntu_installer = config.get("enable_ubuntu_installer_attach", False)

    for name, unit_status in units.items():
        for service in DEFAULT_SERVICES:
            try:
                juju.ssh(name, f"systemctl is-active {service}.service")
            except Exception as e:
                pytest.fail(f"Failed to run command on unit: {e}")

        if enable_ubuntu_installer:
            try:
                juju.ssh(
                    name,
                    f"systemctl is-active {LANDSCAPE_UBUNTU_INSTALLER_ATTACH}.service",
                )
            except Exception as e:
                pytest.fail(f"Failed to run command on unit: {e}")

        if unit_status.leader:
            for service in LEADER_SERVICES:
                try:
                    juju.ssh(name, f"systemctl is-active {service}.service")
                except Exception as e:
                    pytest.fail(f"Failed to run command on unit: {e}")


def test_ubuntu_installer_attach_service(juju: jubilant.Juju, bundle: None):
    """
    NOTE: There is not an equivalent hostagent_messenger test because
    that service will run regardless of the config, unlike Ubuntu Installer
    Attach which will actually install/uninstall the package/service in addition
    to creating an HAProxy backend for it.
    """
    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units
    original = juju.config("landscape-server").get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(jubilant.all_active, timeout=300)
        for name in units.keys():
            try:
                juju.ssh(
                    name,
                    f"systemctl is-active {LANDSCAPE_UBUNTU_INSTALLER_ATTACH}.service",
                )

            except Exception as e:
                pytest.fail(f"Failed to run command on unit: {e}")

    finally:
        restore_val = "true" if original else "false"
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": restore_val}
        )
        juju.wait(jubilant.all_active, timeout=300)


def test_ubuntu_installer_attach_toggle_no_maintenance(
    juju: jubilant.Juju, bundle: None
):
    """
    Toggling Ubuntu Installer Attach should return to active status and
    reflect the correct service state.
    """
    juju.wait(jubilant.all_active, timeout=300)
    config = juju.config("landscape-server")
    original_installer = config.get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "true"}
        )
        juju.wait(jubilant.all_active, timeout=300)

        status = juju.status()
        assert status.apps["landscape-server"].app_status.current == "active"

        for name in status.apps["landscape-server"].units.keys():
            juju.ssh(
                name,
                f"systemctl is-active {LANDSCAPE_UBUNTU_INSTALLER_ATTACH}.service",
            )

        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": "false"}
        )
        juju.wait(jubilant.all_active, timeout=300)

        status = juju.status()
        assert status.apps["landscape-server"].app_status.current == "active"

        for name in status.apps["landscape-server"].units.keys():
            with pytest.raises(Exception):
                juju.ssh(
                    name,
                    f"systemctl is-active {LANDSCAPE_UBUNTU_INSTALLER_ATTACH}.service",
                )

    finally:
        restore_val = "true" if original_installer else "false"
        juju.config(
            "landscape-server", values={"enable_ubuntu_installer_attach": restore_val}
        )
        juju.wait(jubilant.all_active, timeout=300)


def test_non_leader_unit_redirects_leader_only_services(
    juju: jubilant.Juju, bundle: None
):
    status = juju.status()
    units = status.apps["landscape-server"].units

    if len(units) <= 1:
        pytest.skip("Need more than 1 unit to have a non-leader!")

    juju.wait(jubilant.all_active, timeout=300)

    for name, unit_status in units.items():
        if not unit_status.leader:
            host = juju.status().apps["landscape-server"].units[name].public_address

            assert juju.wait(jubilant.all_active, timeout=300) and (
                get_session().get(f"https://{host}/upload", verify=False).status_code
                == 200
            )


def _has_tls_certs_provider(juju: jubilant.Juju) -> bool:
    status = juju.status()

    return any(
        any(rel.interface == "tls-certificates" for rel in rels)
        for rels in status.apps["landscape-server"].relations.values()
    )


def test_get_certificates_action_without_tls_relation(
    juju: jubilant.Juju, bundle: None
):
    status = juju.status()
    juju.wait(jubilant.all_active, timeout=300)

    has_tls_cert_relation = _has_tls_certs_provider(juju)
    original_cert_provider = None

    if has_tls_cert_relation:
        cert_provider = None
        for app_name, app_status in status.apps.items():
            if app_name == "landscape-server":
                continue
            for rels in app_status.relations.values():
                if any(rel.interface == "tls-certificates" for rel in rels):
                    cert_provider = app_name
                    break

            if cert_provider:
                break  # We're allowed to have one

        assert cert_provider is not None
        original_cert_provider = cert_provider

        juju.remove_relation(
            "landscape-server:load-balancer-certificates",
            f"{cert_provider}:certificates",
            force=True,
        )
        juju.wait(lambda status: not _has_tls_certs_provider(juju), timeout=120)

    with pytest.raises(jubilant.TaskError) as e:
        juju.run("landscape-server/0", "get-certificates")

    assert "No assigned TLS certificate found for this unit" in e.value.task.message
    assert e.value.task.status == "failed"

    if original_cert_provider:
        juju.integrate(
            "landscape-server:load-balancer-certificates",
            f"{original_cert_provider}:certificates",
        )
        juju.wait(lambda status: _has_tls_certs_provider(juju), timeout=120)


def test_get_certificates_action_with_tls_relation(juju: jubilant.Juju, bundle: None):
    juju.wait(jubilant.all_active, timeout=300)

    if not _has_tls_certs_provider(juju):
        pytest.skip("No TLS certificate relation found in bundle")

    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    leader_unit = None
    for unit_name, unit_status in status.apps["landscape-server"].units.items():
        if unit_status.leader:
            leader_unit = unit_name
            break

    assert leader_unit is not None

    max_attempts = 12
    result = None
    for attempt in range(max_attempts):
        try:
            result = juju.run(leader_unit, "get-certificates")
            if result.status == "completed":
                break
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(5)
                status = juju.status()
                for unit_name, unit_status in status.apps[
                    "landscape-server"
                ].units.items():
                    if unit_status.leader:
                        leader_unit = unit_name
                        break
            else:
                raise

    assert result is not None
    assert result.status == "completed"
    assert "certificate" in result.results
    assert "ca" in result.results
    assert "chain" in result.results


def test_get_certificates_action_on_non_leader_unit(juju: jubilant.Juju, bundle: None):
    status = juju.status()
    juju.wait(jubilant.all_active, timeout=300)

    if not _has_tls_certs_provider(juju):
        pytest.skip("No TLS certificate relation found in bundle")

    status = juju.status()
    non_leader_units = [
        unit_name
        for unit_name, unit_status in status.apps["landscape-server"].units.items()
        if not unit_status.leader
    ]

    if not non_leader_units:
        pytest.skip("No non-leader units found")

    juju.wait(jubilant.all_active, timeout=300)

    result = juju.run(non_leader_units[0], "get-certificates")

    assert result.status == "completed"
    assert "certificate" in result.results
    assert "ca" in result.results
    assert "chain" in result.results


def test_grpc_ingress_config_enabled(juju: jubilant.Juju, bundle: None):
    """
    Verify that when ingress configs are enabled, the charm creates the ingress
    relations and publishes the correct data to the relation databags.
    """
    status = juju.status()
    app_status = status.apps["landscape-server"]
    if (
        "hostagent-messenger-ingress" not in app_status.relations
        or "ubuntu-installer-attach-ingress" not in app_status.relations
    ):
        pytest.skip("gRPC ingress not integrated, skipping...")

    juju.wait(jubilant.all_active, timeout=300)
    config = juju.config("landscape-server")
    original_hostagent = config.get("enable_hostagent_messenger")
    original_installer = config.get("enable_ubuntu_installer_attach")

    try:
        juju.config(
            "landscape-server",
            values={
                "enable_hostagent_messenger": "true",
                "enable_ubuntu_installer_attach": "true",
            },
        )
        juju.wait(jubilant.all_active, timeout=300)
        status = juju.status()
        app_status = status.apps["landscape-server"]
        assert "hostagent-messenger-ingress" in app_status.relations
        assert "ubuntu-installer-attach-ingress" in app_status.relations

        leader_unit_name = None
        for name, unit_status in app_status.units.items():
            if unit_status.leader:
                leader_unit_name = name
                break

        if not leader_unit_name:
            pytest.fail("No leader unit found for landscape-server")

        def get_relation_data(endpoint):
            ids_stdout = juju.cli(
                "exec", "--unit", leader_unit_name, "--", f"relation-ids {endpoint}"
            )
            ids = ids_stdout.strip().splitlines()
            if not ids:
                pytest.fail(f"No relation IDs found for endpoint {endpoint}")
            rel_id = ids[0]
            data_stdout = juju.cli(
                "exec",
                "--unit",
                leader_unit_name,
                "--",
                f"relation-get --format=json -r {rel_id} --app - {leader_unit_name}",
            )
            data = json.loads(data_stdout)

            return {
                k: v.strip('"') if isinstance(v, str) else v for k, v in data.items()
            }

        hostagent_data = get_relation_data("hostagent-messenger-ingress")

        assert (
            hostagent_data.get("port") == "6554"
        ), f"Expected port 6554, got {hostagent_data.get('port')}"
        assert (
            hostagent_data.get("scheme") == "https"
        ), f"Expected scheme https, got {hostagent_data.get('scheme')}"
        assert hostagent_data.get("name") == "landscape-server"

        installer_data = get_relation_data("ubuntu-installer-attach-ingress")

        assert (
            installer_data.get("port") == "50051"
        ), f"Expected port 50051, got {installer_data.get('port')}"
        assert (
            installer_data.get("scheme") == "https"
        ), f"Expected scheme https, got {installer_data.get('scheme')}"
        assert installer_data.get("name") == "landscape-server"

    finally:
        juju.config(
            "landscape-server",
            values={
                "enable_hostagent_messenger": "true" if original_hostagent else "false",
                "enable_ubuntu_installer_attach": (
                    "true" if original_installer else "false"
                ),
            },
        )
        juju.wait(jubilant.all_active, timeout=300)


def test_haproxy_installed_and_configured(juju: jubilant.Juju, bundle: None):
    juju.wait(jubilant.all_active, timeout=300)

    status = juju.status()
    units = status.apps["landscape-server"].units

    for unit_name in units.keys():
        try:
            juju.ssh(unit_name, f"dpkg -l | grep -q {haproxy.HAPROXY_APT_PACKAGE_NAME}")
        except Exception as e:
            pytest.fail(f"HAProxy not installed on {unit_name}: {e}")

        try:
            juju.ssh(
                unit_name,
                f"sudo {haproxy.HAPROXY_EXECUTABLE} -c -f "
                f"{haproxy.HAPROXY_RENDERED_CONFIG_PATH}",
            )
        except Exception as e:
            pytest.fail(f"HAProxy config validation failed on {unit_name}: {e}")

        for error_file in haproxy.ERROR_FILES["files"].values():
            try:
                juju.ssh(
                    unit_name, f"test -f {haproxy.ERROR_FILES['location']}/{error_file}"
                )
            except Exception:
                pytest.fail(f"Error file missing on {unit_name}: {error_file}")

        try:
            juju.ssh(unit_name, f"systemctl is-active {haproxy.HAPROXY_SERVICE}")
        except Exception as e:
            pytest.fail(f"HAProxy service not active on {unit_name}: {e}")
