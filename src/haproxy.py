from dataclasses import dataclass, field
from enum import Enum
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
HAPROXY_CERT_PATH = "/etc/haproxy/haproxy.pem"
HAPROXY_RENDERED_CONFIG_PATH = "/etc/haproxy/haproxy.cfg"
HAPROXY_USER = "haproxy"
HAPROXY_SERVICE = "haproxy"
HAPROXY_EXECUTABLE = "/usr/sbin/haproxy"
HAPROXY_TMPL = Path("haproxy.cfg.j2")


class HAProxyError(Exception):
    """
    Errors raised when interacting with the local HAProxy service.
    """


class ACL(str, Enum):
    """HAProxy ACLs for Landscape service routing."""

    API = "api"
    ATTACHMENT = "attachment"
    HASHIDS = "hashids"
    MESSAGE = "message"
    PACKAGE_UPLOAD = "package-upload"
    PING = "ping"
    REPOSITORY = "repository"

    def __str__(self) -> str:
        return self.value


class HTTPBackend(str, Enum):
    """HTTP backend identifiers."""

    API = "landscape-http-api"
    HASHIDS = "landscape-http-hashid-databases"
    MESSAGE = "landscape-http-message"
    PACKAGE_UPLOAD = "landscape-http-package-upload"
    PING = "landscape-http-ping"

    def __str__(self) -> str:
        return self.value


class HTTPSBackend(str, Enum):
    """HTTPS backend identifiers."""

    API = "landscape-https-api"
    HASHIDS = "landscape-https-hashid-databases"
    MESSAGE = "landscape-https-message"
    PACKAGE_UPLOAD = "landscape-https-package-upload"
    PING = "landscape-https-ping"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Service:
    """An HAProxy service configuration."""

    service_name: str
    service_host: str
    service_port: int
    server_options: list[str] = field(default_factory=list)
    service_options: list[str] = field(default_factory=list)


CLIENT_TIMEOUT = 300000  # ms
SERVER_TIMEOUT = 300000  # ms
DEFAULT_REDIRECT_SCHEME = "redirect scheme https unless ping OR repository"
GRPC_SERVER_OPTIONS = "proto h2"
SERVER_OPTIONS = "check inter 5000 rise 2 fall 5 maxconn 50"
"""
NOTE: maxconn here is per-server, not global HAProxy maxconn (charm config).
"""


HTTP_SERVICE = Service(
    service_name="landscape-http",
    service_host="0.0.0.0",
    service_port=80,
    service_options=[
        "mode http",
        f"timeout client {CLIENT_TIMEOUT}",
        "balance leastconn",
        "option httpchk HEAD / HTTP/1.0",
        # ACLs
        f"acl {ACL.PING} path_beg -i /ping",
        f"acl {ACL.REPOSITORY} path_beg -i /repository",
        f"acl {ACL.MESSAGE} path_beg -i /message-system",
        f"acl {ACL.ATTACHMENT} path_beg -i /attachment",
        f"acl {ACL.API} path_beg -i /api",
        f"acl {ACL.HASHIDS} path_beg -i /hash-id-databases",
        f"acl {ACL.PACKAGE_UPLOAD} path_beg -i /upload",
        # Rewrite rules
        "http-request replace-path ^([^\\ ]*)\\ /upload/(.*) /\\1",
        # Backends
        f"use_backend {HTTPBackend.MESSAGE} if {ACL.MESSAGE}",
        f"use_backend {HTTPBackend.MESSAGE} if {ACL.ATTACHMENT}",
        f"use_backend {HTTPBackend.API} if {ACL.API}",
        f"use_backend {HTTPBackend.PING} if {ACL.PING}",
        f"use_backend {HTTPBackend.HASHIDS} if {ACL.HASHIDS}",
        f"use_backend {HTTPBackend.PACKAGE_UPLOAD} if {ACL.PACKAGE_UPLOAD}",
        # Metrics
        "acl metrics path_end /metrics",
        "http-request deny if metrics",
        "acl prometheus_metrics path_beg -i /metrics",
        "http-request deny if prometheus_metrics",
    ],
)


HTTPS_SERVICE = Service(
    service_name="landscape-https",
    service_host="0.0.0.0",
    service_port=443,
    service_options=[
        "mode http",
        f"timeout client {CLIENT_TIMEOUT}",
        "balance leastconn",
        "option httpchk HEAD / HTTP/1.0",
        "http-request set-header X-Forwarded-Proto https",
        # ACLs
        f"acl {ACL.PING} path_beg -i /ping",
        f"acl {ACL.REPOSITORY} path_beg -i /repository",
        f"acl {ACL.MESSAGE} path_beg -i /message-system",
        f"acl {ACL.ATTACHMENT} path_beg -i /attachment",
        f"acl {ACL.API} path_beg -i /api",
        f"acl {ACL.HASHIDS} path_beg -i /hash-id-databases",
        f"acl {ACL.PACKAGE_UPLOAD} path_beg -i /upload",
        # Rewrite rules
        "http-request replace-path ^([^\\ ]*)\\ /upload/(.*) /\\1",
        # Backends
        f"use_backend {HTTPSBackend.MESSAGE} if {ACL.MESSAGE}",
        f"use_backend {HTTPSBackend.MESSAGE} if {ACL.ATTACHMENT}",
        f"use_backend {HTTPSBackend.API} if {ACL.API}",
        f"use_backend {HTTPSBackend.PING} if {ACL.PING}",
        f"use_backend {HTTPSBackend.HASHIDS} if {ACL.HASHIDS}",
        f"use_backend {HTTPSBackend.PACKAGE_UPLOAD} if {ACL.PACKAGE_UPLOAD}",
        # Metrics
        "acl metrics path_end /metrics",
        "http-request deny if metrics",
        "acl prometheus_metrics path_beg -i /metrics",
        "http-request deny if prometheus_metrics",
    ],
)

GRPC_SERVICE = Service(
    service_name="landscape-grpc",
    service_host="0.0.0.0",
    service_port=6554,
    server_options=GRPC_SERVER_OPTIONS,
    service_options=["mode http"],
)


UBUNTU_INSTALLER_ATTACH_SERVICE = Service(
    service_name="landscape-ubuntu-installer-attach",
    service_host="0.0.0.0",
    service_port=50051,
    server_options=GRPC_SERVER_OPTIONS,
    service_options=[
        "mode http",
        # The X-FQDN header is required for multitenant installations
        "acl host_found hdr(host) -m found",
        "http-request set-var(req.full_fqdn) hdr(authority) if !host_found",
        "http-request set-var(req.full_fqdn) hdr(host) if host_found",
        "http-request set-header X-FQDN %[var(req.full_fqdn)]",
    ],
)


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

# TODO: Make service base port configurable
PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
    "package-upload": 9100,
    "hostagent-messenger": 50052,
    "ubuntu-installer-attach": 53354,
}


def get_global_options(max_connections: int = 4096) -> list[str]:
    """Get the global HAProxy configuration options, used to inject
    the charm config's `max_global_haproxy_connections`.

    :param max_connections: Max concurrent connections for the entire HAProxy process,
        defaults to 4096
    :return: A list of options to use for the global HAProxy section.
    """
    return [
        "log /dev/log local0",
        "log /dev/log local1 notice",
        f"maxconn {max_connections}",
        "user haproxy",
        "group haproxy",
        "spread-checks 0",
    ]


DEFAULT_OPTIONS = [
    "log global",
    "mode http",
    "option httplog",
    "option dontlognull",
    "retries 3",
    "timeout queue 60000",
    "timeout connect 5000",
    "timeout client 120000",
    "timeout server 120000",
]
"""Options for the HAProxy `defaults` section."""


def get_redirect_directive(redirect_https: RedirectHTTPS) -> str | None:
    """Get the redirect directive based on the redirect_https setting.

    :param redirect_https: The redirect HTTPS configuration
    :return: The redirect directive string, or None if no redirect
    """
    if redirect_https == RedirectHTTPS.ALL:
        return "redirect scheme https"

    if redirect_https == RedirectHTTPS.DEFAULT:
        return DEFAULT_REDIRECT_SCHEME

    return None


def write_file(content: bytes, path: str, permissions=0o600, user=HAPROXY_USER) -> None:
    """
    :raises ValueError: Given content is not bytes!
    :raises OSError: Error reading or writing file or creating directories.
    """
    if not isinstance(content, bytes):
        raise ValueError(f"Invalid file content type: {type(content)}")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)

    os.chmod(path, permissions)
    u = pwd.getpwnam(user)
    os.chown(path, uid=u.pw_uid, gid=u.pw_gid)


def write_ssl_cert(
    encoded_ssl_cert_content: bytes, cert_path=HAPROXY_CERT_PATH
) -> None:
    """
    :raises ValueError: Given content is not bytes!
    :raises OSError: Error reading or writing file or creating directories.
    """
    write_file(
        encoded_ssl_cert_content,
        cert_path,
    )


def copy_error_files_from_source(
    error_src: str, error_files_config: dict = ERROR_FILES
) -> list[str]:
    """Copy HAProxy error files from a source directory into the configured
    HAProxy errors location.

    :param error_src: Path to source directory containing error files.
    :param error_files_config: Mapping with keys `location` and `files`.
    :return written_files: List of destination file paths that were written.
    :raises HAProxyError: Error while copying.
    """
    dst_root = error_files_config.get("location", ERROR_FILES["location"])
    written_files = []

    try:
        for filename in error_files_config.get("files", {}).values():
            src_file = os.path.join(error_src, filename)
            dst_file = os.path.join(dst_root, filename)
            if os.path.exists(src_file):
                with open(src_file, "rb") as f:
                    fp = f.read()
                    write_file(fp, dst_file)
                    written_files.append(dst_file)

    except OSError as e:
        raise HAProxyError(f"Failed to copy error files to HAProxy: {e}")

    return written_files


def render_config(
    all_ips: list[IPvAnyAddress],
    leader_ip: list[IPvAnyAddress],
    worker_counts: int,
    redirect_https: RedirectHTTPS,
    enable_hostagent_messenger: bool,
    enable_ubuntu_installer_attach: bool,
    max_connections: int = 4096,
    ssl_cert_path=HAPROXY_CERT_PATH,
    rendered_config_path: str = HAPROXY_RENDERED_CONFIG_PATH,
    ports=PORTS,
    error_files_root=ERROR_FILES["location"],
    error_files=ERROR_FILES["files"],
    default_options: list[str] = DEFAULT_OPTIONS,
    default_server_timeout: int = SERVER_TIMEOUT,
    default_server_options: str = SERVER_OPTIONS,
    template_path: Path = HAPROXY_TMPL,
    http_service: Service = HTTP_SERVICE,
    https_service: Service = HTTPS_SERVICE,
    grpc_service: Service = GRPC_SERVICE,
    ubuntu_installer_attach_service: Service = UBUNTU_INSTALLER_ATTACH_SERVICE,
) -> str:
    """Render the HAProxy config with the
    given context.

    :param all_ips: A list of IP addresses of the units
    :param leader_ip: The IP of the leader unit
    :param worker_counts: The number of worker processes configured
    :param redirect_https: Whether to redirect HTTP to HTTPS
    :param enable_hostagent_messenger: Whether to create a backend for the
        hostagent messenger service
    :param enable_ubuntu_installer_attach: Whether to create a backend for the
        Ubuntu Installer Attach service
    :param max_connections: Maximum concurrent connections for HAProxy, defaults to 4096
    :param ssl_cert_path: The path of the SSL certificate to use for the HAProxy service,
        defaults to HAPROXY_CERT_PATH
    :param rendered_config_path: Path where the rendered config will be written, defaults to HAPROXY_RENDERED_CONFIG_PATH
    :param ports: A mapping of services to their base ports, defaults to PORTS
    :param error_files_root: Directory where the Landscape error files are, defaults
        to ERROR_FILES["location"]
    :param error_files: A mapping of status codes (string) to the name of the error file in
        `error_files_root`, defaults to ERROR_FILES["files"]
    :param default_options: Options for the HAProxy defaults section, defaults to DEFAULT_OPTIONS
    :param default_server_timeout: Timeout for backend servers in milliseconds, defaults to SERVER_TIMEOUT
    :param default_server_options: Options for all backend servers, defaults to SERVER_OPTIONS
    :param template_path: Path to the Jinja2 template file, defaults to HAPROXY_TMPL
    :param http_service: HTTP service configuration, defaults to HTTP_SERVICE
    :param https_service: HTTPS service configuration, defaults to HTTPS_SERVICE
    :param grpc_service: gRPC service configuration, defaults to GRPC_SERVICE
    :param ubuntu_installer_attach_service: Ubuntu Installer Attach service configuration, defaults to UBUNTU_INSTALLER_ATTACH_SERVICE

    :return rendered: The rendered string given the context.
    """
    global_options = get_global_options(max_connections)

    redirect_directive = get_redirect_directive(redirect_https)

    template_file_path = os.path.join(os.path.dirname(__file__), template_path.name)
    with open(template_file_path) as f:
        template_content = f.read()

    template = Template(template_content)

    context = {
        "peer_ips": all_ips,
        "leader_address": leader_ip,
        "worker_counts": worker_counts,
        "ports": ports,
        "ssl_cert_path": ssl_cert_path,
        "redirect_directive": redirect_directive,
        "error_files_root": error_files_root,
        "error_files": error_files,
        "enable_hostagent_messenger": enable_hostagent_messenger,
        "enable_ubuntu_installer_attach": enable_ubuntu_installer_attach,
        "global_options": global_options,
        "default_options": default_options,
        "default_server_timeout": default_server_timeout,
        "default_server_options": default_server_options,
        "http_service": http_service,
        "https_service": https_service,
        "grpc_service": grpc_service,
        "ubuntu_installer_attach_service": ubuntu_installer_attach_service,
    }

    rendered = template.render(context)

    if not rendered.endswith("\n"):
        rendered += "\n"

    write_file(rendered.encode(), rendered_config_path, 0o644)

    validate_config(rendered_config_path)

    return rendered


def reload(service_name=HAPROXY_SERVICE) -> None:
    """Reloads the HAProxy service.

    :raises HAProxyError: Failed to reload the service!
    """
    try:
        systemd.service_reload(service_name)
    except systemd.SystemdError as e:
        raise HAProxyError(f"Failed reloading the HAProxy service: {str(e)}")


def validate_config(
    config_path: str, haproxy_executable=HAPROXY_EXECUTABLE, user=HAPROXY_USER
) -> None:
    """Validates the HAProxy config.

    :param config_path: Path to the HAProxy config to validate.
    :raises HAProxyError: Failed to validate the HAProxy config!
    """
    try:
        subprocess.run(
            [haproxy_executable, "-c", "-f", config_path],
            capture_output=True,
            check=True,
            user=user,
            text=True,
        )

    except CalledProcessError as e:
        raise HAProxyError(f"Failed to validate HAProxy config: {str(e.output)}")
