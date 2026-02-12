from configparser import ConfigParser
from datetime import timedelta
import json
import pwd
import subprocess
from typing import Any
from unittest.mock import MagicMock, Mock

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    CertificateRequestAttributes,
    CertificateSigningRequest,
    PrivateKey,
)
import pytest
import scenario

import haproxy
import settings_files


class ConfigReader:

    def __init__(self, tempfile):
        self.tempfile = tempfile

    def get_config(self) -> ConfigParser:
        config = ConfigParser()
        config.read(self.tempfile)
        return config


@pytest.fixture(autouse=True)
def capture_service_conf(tmp_path, monkeypatch) -> ConfigReader:
    """
    Redirect all writes to `SERVICE_CONF` to a tempfile within this fixture.
    Return a `ConfigReader` that reads from this file.

    This is set to `autouse=True` to avoid any attempts to write to the filesystem
    during tests, which typically throw an error if the real
    `/etc/landscape/service.conf` is not present.
    """
    conf_file = tmp_path / "service.conf"
    conf_file.write_text("")

    monkeypatch.setattr(settings_files, "SERVICE_CONF", str(conf_file))

    return ConfigReader(conf_file)


# Based on:
# https://github.com/canonical/haproxy-operator/blob/main/haproxy-operator/tests/unit/conftest.py

TEST_CN = "landscape.local"


@pytest.fixture(scope="function", name="ca_certificate_and_key")
def ca_certificate_and_key_fixture() -> tuple[Certificate, PrivateKey]:
    """Ca Certificate and private key."""
    private_key_ca = PrivateKey.generate()
    ca = Certificate.generate_self_signed_ca(
        CertificateRequestAttributes(common_name=TEST_CN),
        PrivateKey.generate(),
        timedelta(days=10),
    )
    return ca, private_key_ca


@pytest.fixture(scope="function", name="csr_certificate_and_key")
def csr_certificate_and_key_fixture(
    ca_certificate_and_key,
) -> tuple[CertificateSigningRequest, Certificate, PrivateKey]:
    """Ca Certificate and private key."""
    ca, private_key_ca = ca_certificate_and_key
    private_key = PrivateKey.generate()
    csr = CertificateRequestAttributes.generate_csr(
        CertificateRequestAttributes(common_name=TEST_CN), private_key
    )
    certificate = Certificate.generate(csr, ca, private_key_ca, timedelta(days=5))
    return csr, certificate, private_key


@pytest.fixture(scope="function", name="certificates_relation_data")
def certificates_relation_data_fixture(
    csr_certificate_and_key,
    ca_certificate_and_key,
) -> dict[str, str]:
    """Mock tls_certificates relation data."""
    csr, cert, _ = csr_certificate_and_key
    ca_cert, _ = ca_certificate_and_key
    return {
        "certificates": json.dumps(
            [
                {
                    "ca": ca_cert.raw,
                    "certificate_signing_request": csr.raw,
                    "certificate": cert.raw,
                    "chain": [
                        cert.raw,
                        ca_cert.raw,
                    ],
                },
            ]
        )
    }


@pytest.fixture(name="certificates_integration")
def certificates_integration_fixture(
    certificates_relation_data, csr_certificate_and_key
):
    csr, _, _ = csr_certificate_and_key
    return scenario.Relation(
        endpoint="load-balancer-certificates",
        remote_app_data=certificates_relation_data,
        local_unit_data={
            "certificate_signing_requests": json.dumps(
                [
                    {
                        "certificate_signing_request": csr.raw,
                        "ca": False,
                    },
                ]
            )
        },
    )


@pytest.fixture(scope="function", name="certificate_and_key_fixture")
def certificate_and_key_fixture(
    monkeypatch: pytest.MonkeyPatch,
    csr_certificate_and_key,
    ca_certificate_and_key,
) -> tuple[Mock, PrivateKey]:
    _, certificate, private_key = csr_certificate_and_key
    ca_cert, _ = ca_certificate_and_key

    provider_cert_mock = Mock(
        certificate=certificate,
        ca=ca_cert,
        chain=[certificate, ca_cert],
    )
    monkeypatch.setattr(
        (
            "charmlibs.interfaces.tls_certificates"
            ".TLSCertificatesRequiresV4.get_assigned_certificate"
        ),
        lambda *args, **kwargs: (provider_cert_mock, private_key),
    )
    monkeypatch.setattr(
        (
            "charmlibs.interfaces.tls_certificates"
            ".TLSCertificatesRequiresV4.get_assigned_certificates"
        ),
        lambda *args, **kwargs: ([provider_cert_mock], private_key),
    )
    return provider_cert_mock, private_key


@pytest.fixture()
def haproxy_user_fixture(monkeypatch):
    monkeypatch.setattr(pwd, "getpwnam", Mock())


@pytest.fixture()
def haproxy_paths_fixture(tmp_path, monkeypatch):
    """Mock HAProxy file paths to use tmp_path fixture."""
    monkeypatch.setattr(haproxy, "HAPROXY_CERT_PATH", str(tmp_path / "haproxy.pem"))
    monkeypatch.setattr(
        haproxy, "HAPROXY_RENDERED_CONFIG_PATH", str(tmp_path / "haproxy.cfg")
    )


@pytest.fixture()
def haproxy_write_tls_cert_fixture(request, monkeypatch) -> Mock:
    mock_write_tls = Mock()
    if not request.node.get_closest_marker("disable_haproxy_mocks"):
        monkeypatch.setattr("haproxy.write_tls_cert", mock_write_tls)

    return mock_write_tls


@pytest.fixture()
def haproxy_write_file_fixture(request, monkeypatch):
    """
    Mock HAProxy file ownership operations that require root permissions.
    """
    if not request.node.get_closest_marker("disable_haproxy_mocks"):
        monkeypatch.setattr("haproxy.write_file", lambda *args, **kwargs: None)


@pytest.fixture(autouse=True)
def haproxy_root_fixture(
    haproxy_paths_fixture,
    haproxy_user_fixture,
    haproxy_write_file_fixture,
    haproxy_write_tls_cert_fixture,
    ownership_fixture,
    check_haproxy_installed,
    haproxy_install_fixture,
    haproxy_copy_error_files_fixture,
) -> tuple[Any, Any, Any, Any, Any, Any, Any, Any]:
    """
    Uses all the given fixtures automatically for all tests.
    Returns the mocks as a tuple for tests that need to access them directly.
    """
    return (
        haproxy_paths_fixture,
        haproxy_user_fixture,
        haproxy_write_file_fixture,
        haproxy_write_tls_cert_fixture,
        ownership_fixture,
        check_haproxy_installed,
        haproxy_install_fixture,
        haproxy_copy_error_files_fixture,
    )


@pytest.fixture()
def ownership_fixture(monkeypatch) -> tuple[Mock, Mock, Mock]:
    """
    Mock os.chown, os.chmod, and shutil.chown
    to avoid doing ownership operations on files in unit tests.

    Returns the mocks for os.chown, os.chmod, and shutil.chown.
    """
    os_chown_mock = Mock()
    monkeypatch.setattr("os.chown", os_chown_mock)

    os_chmod_mock = Mock()
    monkeypatch.setattr("os.chmod", os_chmod_mock)

    shutil_chown_mock = Mock()
    monkeypatch.setattr("shutil.chown", shutil_chown_mock)

    return os_chown_mock, os_chmod_mock, shutil_chown_mock


@pytest.fixture(autouse=True, name="subprocess_fixture")
def subprocess_fixture(monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, stdout=""),
    )


@pytest.fixture(autouse=True, name="check_call_fixture")
def check_call_fixture(monkeypatch):
    monkeypatch.setattr("charm.check_call", lambda *args, **kwargs: None)


@pytest.fixture(name="replicas_networks")
def replicas_networks_fixture():
    """
    Note: The addresses already have defaults.
    """
    # We need this for `unit_ip` and `peer_ips`
    return scenario.Network(
        binding_name="replicas",
    )


@pytest.fixture(name="lb_certs_state")
def lb_certs_state_fixture(
    certificates_integration,
    replicas,
    replicas_networks,
    haproxy_root_fixture,
) -> dict:

    return {
        "relations": [certificates_integration, replicas],
        "networks": [replicas_networks],
    }


@pytest.fixture(name="replicas")
def replicas_fixture() -> scenario.PeerRelation:
    return scenario.PeerRelation(
        endpoint="replicas",
        peers_data={},
    )


@pytest.fixture(name="systemd_fixture")
def systemd_fixture(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        "charms.operator_libs_linux.v1.systemd.service_reload", MagicMock()
    )


@pytest.fixture(name="apt_fixture")
def apt_fixture(monkeypatch: pytest.MonkeyPatch):
    add_package_mock = MagicMock()
    remove_package_mock = MagicMock()
    monkeypatch.setattr(
        "charms.operator_libs_linux.v0.apt.add_package", add_package_mock
    )
    monkeypatch.setattr(
        "charms.operator_libs_linux.v0.apt.remove_package", remove_package_mock
    )
    return add_package_mock, remove_package_mock


@pytest.fixture(name="check_haproxy_installed")
def check_haproxy_installed_fixture(monkeypatch: pytest.MonkeyPatch) -> Mock:
    check_mock = Mock(return_value=Mock(name="haproxy"))
    monkeypatch.setattr("charm.apt.DebianPackage.from_installed_package", check_mock)

    return check_mock


@pytest.fixture(name="haproxy_install_fixture")
def haproxy_install_fixture(request, monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock_install = Mock()
    if not request.node.get_closest_marker("disable_haproxy_mocks"):
        monkeypatch.setattr("haproxy.install", mock_install)
    return mock_install


@pytest.fixture(name="haproxy_copy_error_files_fixture")
def haproxy_copy_error_files_fixture(request, monkeypatch: pytest.MonkeyPatch) -> Mock:
    mock_copy = Mock(return_value=[])
    if not request.node.get_closest_marker("disable_haproxy_mocks"):
        monkeypatch.setattr("haproxy.copy_error_files_from_source", mock_copy)
    return mock_copy
