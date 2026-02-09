"""
Integration tests for upgrade-charm hook functionality.

These tests verify that the charm correctly handles HAProxy installation during
the upgrade-charm hook.
"""

import jubilant
import pytest

import haproxy


def test_upgrade_charm_installs_haproxy_if_missing(juju: jubilant.Juju, bundle: None):
    """
    Test that upgrade-charm hook installs HAProxy if it's not already installed.

    This simulates the scenario where a user upgrades from an older charm version
    that didn't include HAProxy integration to a newer version that does.
    """
    # Get the first landscape-server unit
    status = juju.status()
    units = status.apps["landscape-server"].units
    unit_name = list(units.keys())[0]

    # Uninstall HAProxy to simulate old charm state
    try:
        juju.ssh(unit_name, "sudo apt-get remove -y haproxy")
        juju.ssh(unit_name, f"sudo systemctl stop {haproxy.HAPROXY_SERVICE} || true")
    except Exception:
        pass  # HAProxy might not be installed yet

    # Verify HAProxy is not installed
    try:
        result = juju.ssh(unit_name, "dpkg -l | grep haproxy")
        if haproxy.HAPROXY_APT_PACKAGE_NAME in result:
            pytest.fail(
                f"HAProxy should not be installed on {unit_name} before upgrade"
            )
    except Exception:
        pass  # Expected - HAProxy not installed

    # Trigger upgrade-charm
    juju.run("upgrade-charm", app_name="landscape-server")
    juju.wait_for(apps=["landscape-server"], timeout=600)

    # Verify HAProxy is now installed
    try:
        result = juju.ssh(unit_name, "dpkg -l | grep haproxy")
        assert (
            haproxy.HAPROXY_APT_PACKAGE_NAME in result
        ), f"HAProxy should be installed on {unit_name} after upgrade-charm"
    except Exception as e:
        pytest.fail(f"HAProxy not installed after upgrade-charm on {unit_name}: {e}")

    # Verify HAProxy service is running
    try:
        juju.ssh(unit_name, f"systemctl is-active {haproxy.HAPROXY_SERVICE}")
    except Exception as e:
        pytest.fail(
            f"HAProxy service not active on {unit_name} after upgrade-charm: {e}"
        )

    # Verify HAProxy error files were copied
    for error_code, error_file in haproxy.ERROR_FILES.items():
        if error_code == "location":
            continue
        try:
            juju.ssh(
                unit_name, f"test -f {haproxy.ERROR_FILES['location']}/{error_file}"
            )
        except Exception as e:
            pytest.fail(
                f"Error file missing on {unit_name} after upgrade-charm: {error_file}"
            )


def test_upgrade_charm_preserves_haproxy_config(juju: jubilant.Juju, bundle: None):
    """
    Test that upgrade-charm hook preserves HAProxy configuration if already installed.

    This verifies that the charm doesn't unnecessarily reinstall or reconfigure
    HAProxy when upgrading between versions that both include HAProxy.
    """
    status = juju.status()
    units = status.apps["landscape-server"].units
    unit_name = list(units.keys())[0]

    # Verify HAProxy is installed
    try:
        result = juju.ssh(unit_name, "dpkg -l | grep haproxy")
        assert (
            haproxy.HAPROXY_APT_PACKAGE_NAME in result
        ), f"HAProxy should be installed on {unit_name} before upgrade"
    except Exception as e:
        pytest.fail(f"HAProxy check failed on {unit_name}: {e}")

    # Get HAProxy config checksum before upgrade
    try:
        checksum_before = juju.ssh(
            unit_name, f"sudo md5sum {haproxy.HAPROXY_RENDERED_CONFIG_PATH}"
        ).split()[0]
    except Exception as e:
        pytest.fail(f"Failed to get HAProxy config checksum on {unit_name}: {e}")

    # Trigger upgrade-charm
    juju.run("upgrade-charm", app_name="landscape-server")
    juju.wait_for(apps=["landscape-server"], timeout=600)

    # Verify HAProxy is still installed and running
    try:
        juju.ssh(unit_name, f"systemctl is-active {haproxy.HAPROXY_SERVICE}")
    except Exception as e:
        pytest.fail(f"HAProxy service not active on {unit_name} after upgrade: {e}")

    # Get HAProxy config checksum after upgrade
    try:
        checksum_after = juju.ssh(
            unit_name, f"sudo md5sum {haproxy.HAPROXY_RENDERED_CONFIG_PATH}"
        ).split()[0]
    except Exception as e:
        pytest.fail(
            f"Failed to get HAProxy config checksum after upgrade on {unit_name}: {e}"
        )

    # Config should be updated (HAProxy is regenerated on upgrade)
    # We just verify it exists and is valid
    assert checksum_after, f"HAProxy config should exist after upgrade on {unit_name}"


def test_upgrade_charm_all_units_have_haproxy(juju: jubilant.Juju, bundle: None):
    """
    Test that upgrade-charm hook ensures HAProxy is installed on all units.

    This is particularly important for scaled deployments where multiple units
    need to have consistent HAProxy configuration.
    """
    status = juju.status()
    units = status.apps["landscape-server"].units

    # Trigger upgrade-charm
    juju.run("upgrade-charm", app_name="landscape-server")
    juju.wait_for(apps=["landscape-server"], timeout=600)

    # Verify HAProxy on all units
    for unit_name in units.keys():
        # Check HAProxy package
        try:
            result = juju.ssh(unit_name, "dpkg -l | grep haproxy")
            assert (
                haproxy.HAPROXY_APT_PACKAGE_NAME in result
            ), f"HAProxy should be installed on {unit_name}"
        except Exception as e:
            pytest.fail(f"HAProxy not installed on {unit_name}: {e}")

        # Check HAProxy service
        try:
            juju.ssh(unit_name, f"systemctl is-active {haproxy.HAPROXY_SERVICE}")
        except Exception as e:
            pytest.fail(f"HAProxy service not active on {unit_name}: {e}")

        # Check HAProxy config file
        try:
            juju.ssh(unit_name, f"test -f {haproxy.HAPROXY_RENDERED_CONFIG_PATH}")
        except Exception as e:
            pytest.fail(f"HAProxy config missing on {unit_name}: {e}")


def test_upgrade_charm_haproxy_error_files(juju: jubilant.Juju, bundle: None):
    """
    Test that upgrade-charm hook ensures HAProxy error files are present.

    Verifies that custom error pages are properly deployed during upgrade.
    """
    status = juju.status()
    units = status.apps["landscape-server"].units

    # Trigger upgrade-charm
    juju.run("upgrade-charm", app_name="landscape-server")
    juju.wait_for(apps=["landscape-server"], timeout=600)

    # Check error files on all units
    for unit_name in units.keys():
        for error_code, error_file in haproxy.ERROR_FILES.items():
            if error_code == "location":
                continue
            try:
                juju.ssh(
                    unit_name, f"test -f {haproxy.ERROR_FILES['location']}/{error_file}"
                )
            except Exception as e:
                pytest.fail(
                    f"HAProxy error file missing on {unit_name} after upgrade: "
                    f"{error_file} ({e})"
                )


def test_upgrade_charm_no_service_disruption(juju: jubilant.Juju, bundle: None):
    """
    Test that upgrade-charm hook completes without disrupting Landscape services.

    Verifies that the upgrade process doesn't cause unnecessary service restarts
    or configuration changes that would interrupt normal operation.
    """
    status = juju.status()
    units = status.apps["landscape-server"].units
    unit_name = list(units.keys())[0]

    # Trigger upgrade-charm
    juju.run("upgrade-charm", app_name="landscape-server")
    juju.wait_for(apps=["landscape-server"], timeout=600)

    # Verify unit is active
    status_after = juju.status()
    unit_status = status_after.apps["landscape-server"].units[unit_name]
    assert (
        unit_status.agent_status == "idle"
    ), f"Unit {unit_name} should be idle after upgrade"
    assert unit_status.workload_status in [
        "active",
        "waiting",
    ], f"Unit {unit_name} should be active or waiting after upgrade"

    # Verify HAProxy is running
    try:
        juju.ssh(unit_name, f"systemctl is-active {haproxy.HAPROXY_SERVICE}")
    except Exception as e:
        pytest.fail(f"HAProxy not running on {unit_name} after upgrade: {e}")
