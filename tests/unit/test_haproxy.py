from ipaddress import IPv4Address
from subprocess import CalledProcessError
from unittest.mock import Mock

from ops.testing import Context, State
import pytest

from charm import LandscapeServerCharm
from config import RedirectHTTPS
import haproxy


class TestPeerIPs:
    def test_peer_ips_multiple_units(self, lb_certs_state):
        context = Context(LandscapeServerCharm)
        state = State(**lb_certs_state)

        with context(context.on.config_changed(), state) as mgr:
            peer_ips = mgr.charm.peer_ips
            assert peer_ips is not None
            assert len(peer_ips.all_ips) >= 1
            assert str(peer_ips.leader_ip) in [str(ip) for ip in peer_ips.all_ips]
            assert peer_ips.leader_ip in peer_ips.all_ips

    def test_peer_ips_returns_non_none_value(self):
        context = Context(LandscapeServerCharm)
        state = State()

        with context(context.on.config_changed(), state) as mgr:
            peer_ips = mgr.charm.peer_ips
            assert peer_ips is not None
            assert isinstance(peer_ips.all_ips, list)
            assert len(peer_ips.all_ips) >= 1
            assert peer_ips.leader_ip in peer_ips.all_ips

    def test_peer_ips_leader_defaults_to_unit_ip(self, lb_certs_state):
        context = Context(LandscapeServerCharm)
        state = State(**lb_certs_state)

        with context(context.on.config_changed(), state) as mgr:
            peer_ips = mgr.charm.peer_ips
            unit_ip = mgr.charm.unit_ip

            assert peer_ips is not None
            assert unit_ip is not None
            assert str(peer_ips.leader_ip) == unit_ip
            assert peer_ips.leader_ip in peer_ips.all_ips

    def test_peer_ips_all_ips_contains_unit_ip(self, lb_certs_state):
        context = Context(LandscapeServerCharm)
        state = State(**lb_certs_state)

        with context(context.on.config_changed(), state) as mgr:
            peer_ips = mgr.charm.peer_ips
            unit_ip = mgr.charm.unit_ip

            assert peer_ips is not None
            assert unit_ip is not None
            assert unit_ip in [str(ip) for ip in peer_ips.all_ips]
            assert peer_ips.leader_ip in peer_ips.all_ips

    def test_peer_ips_excludes_own_unit_from_peers(self, lb_certs_state):
        context = Context(LandscapeServerCharm)
        state = State(**lb_certs_state)

        with context(context.on.config_changed(), state) as mgr:
            peer_ips = mgr.charm.peer_ips
            unit_ip = mgr.charm.unit_ip

            assert peer_ips is not None
            assert unit_ip is not None

            ip_count = sum(1 for ip in peer_ips.all_ips if str(ip) == unit_ip)
            assert ip_count == 1
            assert peer_ips.leader_ip in peer_ips.all_ips


class TestUnitIP:
    def test_unit_ip_returns_valid_ip(self, lb_certs_state):
        context = Context(LandscapeServerCharm)
        state = State(**lb_certs_state)

        with context(context.on.config_changed(), state) as mgr:
            unit_ip = mgr.charm.unit_ip
            assert unit_ip is not None
            assert isinstance(unit_ip, str)
            assert "." in unit_ip or ":" in unit_ip

    def test_unit_ip_in_peer_ips(self, lb_certs_state):
        context = Context(LandscapeServerCharm)
        state = State(**lb_certs_state)

        with context(context.on.config_changed(), state) as mgr:
            unit_ip = mgr.charm.unit_ip
            peer_ips = mgr.charm.peer_ips
            assert unit_ip in [str(ip) for ip in peer_ips.all_ips]


class TestWriteFile:
    def test_write_file_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.chown", Mock())

        file_path = tmp_path / "subdir" / "test.pem"
        content = b"test content"

        haproxy.write_file(content, str(file_path))

        assert file_path.exists()
        assert file_path.read_bytes() == content

    def test_write_file_raises_on_non_bytes(self, tmp_path):
        with pytest.raises(ValueError):
            haproxy.write_file("not bytes", str(tmp_path / "test.pem"))

    def test_write_file_sets_permissions(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.chown", Mock())

        file_path = tmp_path / "test.pem"
        haproxy.write_file(b"content", str(file_path), permissions=0o600)

        mode = file_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestWriteTLSCert:
    def test_write_tls_cert_success(
        self, tmp_path, monkeypatch, certificate_and_key_fixture
    ):
        monkeypatch.setattr("os.chown", Mock())

        cert_path = tmp_path / "cert.pem"
        provider_cert, private_key = certificate_and_key_fixture

        haproxy.write_tls_cert(provider_cert, private_key, str(cert_path))

        assert cert_path.exists()
        content = cert_path.read_text()
        assert len(content) > 0

    def test_write_tls_cert_raises_on_error(self, monkeypatch):
        monkeypatch.setattr(
            "haproxy.write_file", Mock(side_effect=OSError("Permission denied"))
        )

        mock_cert = Mock()
        mock_cert.certificate = "cert"
        mock_key = Mock()
        mock_key.__str__ = Mock(return_value="key")

        with pytest.raises(haproxy.HAProxyError):
            haproxy.write_tls_cert(mock_cert, mock_key)


class TestCopyErrorFilesFromSource:
    def test_copy_error_files_success(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.chown", Mock())

        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()

        (src_dir / "unauthorized-haproxy.html").write_text("<html>403</html>")
        (src_dir / "exception-haproxy.html").write_text("<html>500</html>")

        error_files_config = {
            "location": str(dst_dir),
            "files": {
                "403": "unauthorized-haproxy.html",
                "500": "exception-haproxy.html",
            },
        }

        written = haproxy.copy_error_files_from_source(str(src_dir), error_files_config)

        assert len(written) == 2
        assert (dst_dir / "unauthorized-haproxy.html").exists()
        assert (dst_dir / "exception-haproxy.html").exists()

    def test_copy_error_files_missing_source(self, tmp_path):
        src_dir = tmp_path / "src"
        dst_dir = tmp_path / "dst"
        src_dir.mkdir()

        error_files_config = {
            "location": str(dst_dir),
            "files": {
                "403": "missing.html",
            },
        }

        written = haproxy.copy_error_files_from_source(str(src_dir), error_files_config)

        assert len(written) == 0


class TestGetRedirectDirective:
    def test_redirect_directive_all(self):

        directive = haproxy.get_redirect_directive(RedirectHTTPS.ALL)
        assert directive == "redirect scheme https"

    def test_redirect_directive_default(self):

        directive = haproxy.get_redirect_directive(RedirectHTTPS.DEFAULT)
        assert "redirect scheme https" in directive
        assert "unless ping OR repository" in directive

    def test_redirect_directive_none(self):

        directive = haproxy.get_redirect_directive(RedirectHTTPS.NONE)
        assert directive is None


class TestInstall:
    def test_install_success(self, apt_fixture):
        add_package_mock, _ = apt_fixture
        haproxy.install()
        add_package_mock.assert_called_once_with("haproxy", update_cache=True)

    def test_install_failure(self, monkeypatch):
        from charms.operator_libs_linux.v0 import apt

        monkeypatch.setattr(
            "haproxy.apt.add_package",
            Mock(side_effect=apt.PackageError("E: Unable to locate package")),
        )

        with pytest.raises(haproxy.HAProxyError):
            haproxy.install()


class TestReload:
    def test_reload_success(self):
        haproxy.reload()

    def test_reload_failure(self, monkeypatch):
        from charms.operator_libs_linux.v1 import systemd

        monkeypatch.setattr(
            "haproxy.systemd.service_reload",
            Mock(side_effect=systemd.SystemdError("Failed to reload")),
        )

        with pytest.raises(haproxy.HAProxyError):
            haproxy.reload()


class TestCreateHttpService:
    def test_create_http_service_single_unit(self):
        peer_ips = [IPv4Address("192.0.2.1")]
        leader_ip = IPv4Address("192.0.2.1")
        worker_counts = 2

        service = haproxy.create_http_service(peer_ips, leader_ip, worker_counts)

        assert service.frontend.frontend_name == "landscape-http"
        assert service.frontend.frontend_port == 80
        assert len(service.backends) == 6

        appserver_backend = next(
            b for b in service.backends if "appserver" in b.backend_name
        )
        assert len(appserver_backend.servers) == 2

    def test_create_http_service_multiple_units(self):
        peer_ips = [IPv4Address("192.0.2.1"), IPv4Address("192.0.2.2")]
        leader_ip = IPv4Address("192.0.2.1")
        worker_counts = 1

        service = haproxy.create_http_service(peer_ips, leader_ip, worker_counts)

        appserver_backend = next(
            b for b in service.backends if "appserver" in b.backend_name
        )
        assert len(appserver_backend.servers) == 2

    def test_create_http_service_package_upload_leader_only(self):
        peer_ips = [IPv4Address("192.0.2.1"), IPv4Address("192.0.2.2")]
        leader_ip = IPv4Address("192.0.2.1")
        worker_counts = 1

        service = haproxy.create_http_service(peer_ips, leader_ip, worker_counts)

        upload_backend = next(
            b for b in service.backends if "package-upload" in b.backend_name
        )
        assert len(upload_backend.servers) == 1
        assert upload_backend.servers[0].ip == str(leader_ip)


class TestCreateHttpsService:
    def test_create_https_service_single_unit(self):
        peer_ips = [IPv4Address("192.0.2.1")]
        leader_ip = IPv4Address("192.0.2.1")
        worker_counts = 2

        service = haproxy.create_https_service(peer_ips, leader_ip, worker_counts)

        assert service.frontend.frontend_name == "landscape-https"
        assert service.frontend.frontend_port == 443
        assert len(service.backends) == 6

    def test_create_https_service_hashids_leader_only(self):
        peer_ips = [IPv4Address("192.0.2.1"), IPv4Address("192.0.2.2")]
        leader_ip = IPv4Address("192.0.2.1")
        worker_counts = 1

        service = haproxy.create_https_service(peer_ips, leader_ip, worker_counts)

        hashids_backend = next(
            b for b in service.backends if "hashid" in b.backend_name
        )
        assert len(hashids_backend.servers) == 1
        assert hashids_backend.servers[0].ip == str(leader_ip)

    def test_create_https_service_package_upload_leader_only(self):
        peer_ips = [IPv4Address("192.0.2.1"), IPv4Address("192.0.2.2")]
        leader_ip = IPv4Address("192.0.2.1")
        worker_counts = 1

        service = haproxy.create_https_service(peer_ips, leader_ip, worker_counts)

        upload_backend = next(
            b for b in service.backends if "package-upload" in b.backend_name
        )
        assert len(upload_backend.servers) == 1
        assert upload_backend.servers[0].ip == str(leader_ip)


class TestCreateHostagentMessengerService:
    def test_create_hostagent_messenger_service(self):
        peer_ips = [IPv4Address("192.0.2.1"), IPv4Address("192.0.2.2")]

        service = haproxy.create_hostagent_messenger_service(peer_ips)

        assert (
            service.frontend.frontend_name == haproxy.FrontendName.HOSTAGENT_MESSENGER
        )
        assert service.frontend.frontend_port == 6554
        assert len(service.backends) == 1
        assert (
            service.backends[0].backend_name == haproxy.FrontendName.HOSTAGENT_MESSENGER
        )
        assert len(service.backends[0].servers) == 2
        assert "proto h2" in service.backends[0].servers[0].options


class TestCreateUbuntuInstallerAttachService:
    def test_create_ubuntu_installer_attach_service(self):
        peer_ips = [IPv4Address("192.0.2.1")]

        service = haproxy.create_ubuntu_installer_attach_service(peer_ips)

        assert (
            service.frontend.frontend_name
            == haproxy.FrontendName.UBUNTU_INSTALLER_ATTACH
        )
        assert service.frontend.frontend_port == 50051
        assert len(service.backends) == 1
        assert (
            service.backends[0].backend_name
            == haproxy.FrontendName.UBUNTU_INSTALLER_ATTACH
        )
        assert len(service.backends[0].servers) == 1
        assert haproxy.GRPC_SERVER_OPTIONS in service.backends[0].servers[0].options


class TestValidateConfig:
    def test_validate_config_success(self, subprocess_fixture, tmp_path):
        haproxy.validate_config(str(tmp_path / "haproxy.cfg"))

    def test_validate_config_failure(self, monkeypatch, tmp_path):
        error = CalledProcessError(1, "haproxy")
        error.stdout = ""
        error.stderr = "Error"
        monkeypatch.setattr("subprocess.run", Mock(side_effect=error))

        with pytest.raises(haproxy.HAProxyError):
            haproxy.validate_config(str(tmp_path / "haproxy.cfg"))


class TestRenderConfig:
    def test_render_config_basic(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.chown", Mock())

        template_content = """
global
    maxconn {{ global_max_connections }}

defaults
    mode http

frontend {{ http_service.frontend.frontend_name }}
    bind [::]:{{ http_service.frontend.frontend_port }} v4v6
    default_backend {{ http_service.default_backend }}

backend {{ http_service.backends[0].backend_name }}
    mode http
"""
        template_path = tmp_path / "haproxy.cfg.j2"
        template_path.write_text(template_content)
        monkeypatch.setattr("haproxy.LOCAL_JINJA_TMPL_PATH", str(template_path))

        config_path = tmp_path / "haproxy.cfg"

        rendered = haproxy.render_config(
            all_ips=[IPv4Address("192.0.2.1")],
            leader_ip=IPv4Address("192.0.2.1"),
            worker_counts=1,
            redirect_https=RedirectHTTPS.DEFAULT,
            enable_hostagent_messenger=False,
            enable_ubuntu_installer_attach=False,
            rendered_config_path=str(config_path),
        )

        assert "maxconn 4096" in rendered
        assert "landscape-http" in rendered
        assert config_path.exists()

    def test_render_config_with_hostagent_messenger(self, tmp_path, monkeypatch):
        monkeypatch.setattr("os.chown", Mock())

        template_content = """
{% if hostagent_messenger_service %}
frontend {{ hostagent_messenger_service.frontend.frontend_name }}
    bind [::]:{{ hostagent_messenger_service.frontend.frontend_port }} \
        v4v6 ssl crt /path/to/cert
{% endif %}
"""
        template_path = tmp_path / "haproxy.cfg.j2"
        template_path.write_text(template_content)
        monkeypatch.setattr("haproxy.LOCAL_JINJA_TMPL_PATH", str(template_path))

        config_path = tmp_path / "haproxy.cfg"

        rendered = haproxy.render_config(
            all_ips=[IPv4Address("192.0.2.1")],
            leader_ip=IPv4Address("192.0.2.1"),
            worker_counts=1,
            redirect_https=RedirectHTTPS.DEFAULT,
            enable_hostagent_messenger=True,
            enable_ubuntu_installer_attach=False,
            rendered_config_path=str(config_path),
        )

        assert haproxy.FrontendName.HOSTAGENT_MESSENGER in rendered

    def test_render_config_write_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "haproxy.write_file", Mock(side_effect=OSError("Permission denied"))
        )

        with pytest.raises(haproxy.HAProxyError):
            haproxy.render_config(
                all_ips=[IPv4Address("192.0.2.1")],
                leader_ip=IPv4Address("192.0.2.1"),
                worker_counts=1,
                redirect_https=RedirectHTTPS.DEFAULT,
                enable_hostagent_messenger=False,
                enable_ubuntu_installer_attach=False,
            )
