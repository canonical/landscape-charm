import os
from pathlib import Path
import pwd
import subprocess
from subprocess import CalledProcessError

from charms.operator_libs_linux.v1 import systemd
from jinja2 import Template
from pydantic import IPvAnyAddress

from config import RedirectHTTPS

# Based on: https://github.com/canonical/haproxy-operator/blob/main/haproxy-operator/src/haproxy.py

HAPROXY_APT_PACKAGE_NAME = "haproxy"
HAPROXY_CONFIG_DIR = Path("/etc/haproxy")
HAPROXY_CERT_PATH = "/etc/haproxy/haproxy.pem"
HAPROXY_RENDERED_CONFIG_PATH = Path(HAPROXY_CONFIG_DIR / "haproxy.cfg")
HAPROXY_USER = "haproxy"
HAPROXY_SERVICE = "haproxy"
HAPROXY_EXECUTABLE = "/usr/sbin/haproxy"
HAPROXY_TMPL = Path("haproxy.cfg.j2")


class HAProxyError(Exception):
    """
    Errors raised when interacting with the HAProxy
    systemd service.
    """


ERROR_FILES = {
    "location": "/etc/haproxy/errors",
    "files": {
        "403": "unauthorized-haproxy.html",
        "500": "exception-haproxy.html",
        "502": "unplanned-offline-haproxy.html",
        "503": "unplanned-offline-haproxy.html",
        "504": "timeout-haproxy.html",
    },
}


PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
    "package-upload": 9100,
    "hostagent-messenger": 50052,
    "ubuntu-installer-attach": 53354,
}


def write_ssl_cert(ssl_cert: bytes) -> None:
    os.makedirs(os.path.dirname(HAPROXY_CERT_PATH), exist_ok=True)
    with open(HAPROXY_CERT_PATH, "wb") as ssl_cert_fp:
        ssl_cert_fp.write(ssl_cert)

    os.chmod(HAPROXY_CERT_PATH, 0o600)
    u = pwd.getpwnam(HAPROXY_USER)
    os.chown(HAPROXY_CERT_PATH, uid=u.pw_uid, gid=u.pw_gid)


def render_haproxy_config(
    all_ips: list[IPvAnyAddress],
    leader_ip: list[IPvAnyAddress],
    worker_counts: int,
    redirect_https: RedirectHTTPS,
    enable_hostagent_messenger: bool,
    enable_ubuntu_installer_attach: bool,
) -> None:
    template_path = os.path.join(os.path.dirname(__file__), HAPROXY_TMPL.name)
    with open(template_path) as f:
        template_content = f.read()

    template = Template(template_content)
    rendered = template.render(
        {
            "peer_ips": all_ips,
            "leader_address": leader_ip,
            "worker_counts": worker_counts,
            "ports": PORTS,
            "ssl_cert_path": HAPROXY_CERT_PATH,
            "https_redirect": redirect_https.value,
            "error_files_root": ERROR_FILES["location"],
            "error_files": ERROR_FILES["files"],
            "enable_hostagent_messenger": enable_hostagent_messenger,
            "enable_ubuntu_installer_attach": enable_ubuntu_installer_attach,
        }
    )

    if not rendered.endswith("\n"):
        rendered += "\n"

    HAPROXY_RENDERED_CONFIG_PATH.write_text(rendered, encoding="utf-8")
    os.chmod(HAPROXY_RENDERED_CONFIG_PATH, 0o644)

    u = pwd.getpwnam(HAPROXY_USER)
    os.chown(HAPROXY_RENDERED_CONFIG_PATH, uid=u.pw_uid, gid=u.pw_gid)

    validate_haproxy_config(str(HAPROXY_RENDERED_CONFIG_PATH))


def restart_haproxy() -> None:
    try:
        systemd.service_reload(HAPROXY_SERVICE)
    except systemd.SystemdError as e:
        raise HAProxyError(f"Failed reloading the HAProxy service: {str(e)}")


def validate_haproxy_config(config_path: str) -> None:
    try:
        subprocess.run(
            [HAPROXY_EXECUTABLE, "-c", "-f", config_path],
            capture_output=True,
            check=True,
            user=HAPROXY_USER,
            text=True,
        )

    except CalledProcessError as e:
        raise HAProxyError(f"Failed to validate HAProxy config: {str(e.output)}")
