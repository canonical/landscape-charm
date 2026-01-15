from enum import Enum
import os
import pwd
import shutil
import subprocess
from subprocess import CalledProcessError
from typing import Mapping

from charmlibs.interfaces.tls_certificates import (
    Certificate,
    PrivateKey,
)
from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v1 import systemd
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, IPvAnyAddress

from config import RedirectHTTPS

# Based on: https://github.com/canonical/haproxy-operator/blob/main/haproxy-operator/src/haproxy.py

HAPROXY_APT_PACKAGE_NAME = "haproxy"
HAPROXY_CERT_PATH = "/etc/haproxy/haproxy.pem"
HAPROXY_RENDERED_CONFIG_PATH = "/etc/haproxy/haproxy.cfg"
HAPROXY_USER = "haproxy"
HAPROXY_SERVICE = "haproxy"
HAPROXY_EXECUTABLE = "/usr/sbin/haproxy"
LOCAL_JINJA_TMPL_PATH = "haproxy.cfg.j2"


class HAProxyError(Exception):
    """
    Errors raised when interacting with the local HAProxy service.
    """


class ACL(str, Enum):
    """
    HAProxy ACLs for Landscape service routing.
    """

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

    API = "landscape-http-api"
    APPSERVER = "landscape-http-appserver"
    HASHIDS = "landscape-http-hashid-databases"
    MESSAGE = "landscape-http-message"
    PACKAGE_UPLOAD = "landscape-http-package-upload"
    PING = "landscape-http-ping"

    def __str__(self) -> str:
        return self.value


class HTTPSBackend(str, Enum):

    API = "landscape-https-api"
    APPSERVER = "landscape-https-appserver"
    HASHIDS = "landscape-https-hashid-databases"
    MESSAGE = "landscape-https-message"
    PACKAGE_UPLOAD = "landscape-https-package-upload"
    PING = "landscape-https-ping"

    def __str__(self) -> str:
        return self.value


HOSTAGENT_MESSENGER_BACKEND = "landscape-hostagent-messenger"
UBUNTU_INSTALLER_ATTACH_BACKEND = "landscape-ubuntu-installer-attach"


class FrontendName(str, Enum):
    HOSTAGENT_MESSENGER = "landscape-hostagent-messenger"
    HTTP = "landscape-http"
    HTTPS = "landscape-https"
    UBUNTU_INSTALLER_ATTACH = "landscape-ubuntu-installer-attach"

    def __str__(self) -> str:
        return self.value


class FrontendPort(int, Enum):
    HOSTAGENT_MESSENGER = 6554
    HTTP = 80
    HTTPS = 443
    UBUNTU_INSTALLER_ATTTACH = 50051

    def __int__(self) -> int:
        return self.value


class Server(BaseModel):
    name: str
    ip: str
    port: int
    options: str


class Backend(BaseModel):
    backend_name: str
    servers: list[Server] = []


class Frontend(BaseModel):
    frontend_name: str
    frontend_port: int
    frontend_options: list[str] = []


class Service(BaseModel):
    frontend: Frontend
    backends: list[Backend] = []
    default_backend: str = ""


CLIENT_TIMEOUT = 5 * 60 * 1000  # 5 mins
SERVER_TIMEOUT = 5 * 60 * 1000  # 5 mins
DEFAULT_REDIRECT_SCHEME = "redirect scheme https unless ping OR repository"
GRPC_SERVER_OPTIONS = "proto h2"
"""
Additional configuration for a gRPC server in the HAProxy config.
"""
# NOTE: maxconn here is per-server, not global HAProxy maxconn (charm config).
SERVER_OPTIONS = "check inter 5000 rise 2 fall 5 maxconn 50"
"""
Configuration for a `server` stanza in the HAProxy config.
"""

HTTP_FRONTEND = Frontend(
    frontend_name=FrontendName.HTTP,
    frontend_port=FrontendPort.HTTP,
    frontend_options=[
        "mode http",
        f"timeout client {CLIENT_TIMEOUT}",
        f"timeout server {SERVER_TIMEOUT}",
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
        # Rewrite rules:
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


HTTPS_FRONTEND = Frontend(
    frontend_name=FrontendName.HTTPS,
    frontend_port=FrontendPort.HTTPS,
    frontend_options=[
        "mode http",
        f"timeout client {CLIENT_TIMEOUT}",
        f"timeout server {SERVER_TIMEOUT}",
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
        # Rewrite rules:
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

HOSTAGENT_MESSENGER_FRONTEND = Frontend(
    frontend_name=FrontendName.HOSTAGENT_MESSENGER,
    frontend_port=FrontendPort.HOSTAGENT_MESSENGER,
    frontend_options=["mode http"],
)


UBUNTU_INSTALLER_ATTACH_FRONTEND = Frontend(
    frontend_name=FrontendName.UBUNTU_INSTALLER_ATTACH,
    frontend_port=FrontendPort.UBUNTU_INSTALLER_ATTTACH,
    frontend_options=[
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
SERVICE_PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
    "package-upload": 9100,
    "hostagent-messenger": 50052,
    "ubuntu-installer-attach": 53354,
}

ServicePorts = Mapping[str, int]
"""
Configuration for the ports that Landscape services run on.

Expects the following keys:
- appserver
- pingserver
- message-server
- api
- package-upload
- hostagent-messenger
- ubuntu-installer-attach

Each value is the port that service runs on.
"""


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
    :raises ValueError: Invalid file content type!
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


def write_tls_cert(
    provider_certificate: Certificate,
    private_key: PrivateKey,
    cert_path=HAPROXY_CERT_PATH,
) -> None:
    """
    Combines a TLS certificate and private key pair from a tls-certificates provider,
    encodes it to bytes, and writes it to `cert_path`, where it will be used
    for TLS connections to HAProxy.

    :raises HAProxyError: Failed to write TLS certificate for HAProxy!
    """
    combined_pem = str(provider_certificate.certificate) + "\n" + str(private_key)

    try:
        write_file(
            combined_pem.encode(),
            cert_path,
        )
    except OSError as e:
        raise HAProxyError(f"Failed to write TLS certificate for HAProxy: {str(e)}")


def copy_error_files_from_source(
    src_dir: str, error_files_config: dict = ERROR_FILES
) -> list[str]:
    """
    Copy error files from a source directory (Landscape) into the configured
    HAProxy errors location.

    :param src_dir: Path to source directory containing error files.
    :param error_files_config: Mapping with keys `location` and `files`.

    :return written_files: List of destination file paths that were written.
    :raises HAProxyError: Error while copying.
    """
    dst_dir = error_files_config.get("location", ERROR_FILES["location"])
    written_files = []

    os.makedirs(dst_dir, exist_ok=True)
    for filename in error_files_config.get("files", {}).values():
        src_file = os.path.join(src_dir, filename)
        dst_file = os.path.join(dst_dir, filename)
        if not os.path.exists(src_file):
            continue

        shutil.copy2(src_file, dst_file)
        shutil.chown(dst_file, user=HAPROXY_USER)
        os.chmod(dst_file, 0o600)
        written_files.append(dst_file)

    return written_files


def sanitize_ip(ip: IPvAnyAddress | str) -> str:
    """Return a dash-separated token safe for use in names from an IP.

    Accepts either a string or an IPvAnyAddress-like object. For IPv6 scope
    identifiers (e.g. 'fe80::1%eth0') the scope is appended after a dash.
    Examples:
      '192.0.2.1' -> '192-0-2-1'
      '2001:db8::1' -> '2001-db8--1'
      'fe80::1%eth0' -> 'fe80--1-eth0'
    """
    if not isinstance(ip, str):
        ip = str(ip)

    scope = None
    if "%" in ip:
        ip, scope = ip.split("%", 1)

    cleaned = ip.replace(".", "-").replace(":", "-")

    if scope:
        cleaned = f"{cleaned}-{scope}"

    return cleaned


def format_ip_for_haproxy(ip: IPvAnyAddress | str) -> str:
    """Format IP address for HAProxy server line (wrap IPv6 in brackets).
    This allows us to do {ip}:{port} for IPV6.

    Examples:
      '192.0.2.1' -> '192.0.2.1'
      '2001:db8::1' -> '[2001:db8::1]'
      IPv6Address('2001:db8::1') -> '[2001:db8::1]'
    """
    ip_str = str(ip)
    return f"[{ip_str}]" if ":" in ip_str else ip_str


def create_http_service(
    peer_ips: list[IPvAnyAddress],
    leader_ip: IPvAnyAddress,
    worker_counts: int,
    service_ports: "ServicePorts" = SERVICE_PORTS,
    server_options: str = SERVER_OPTIONS,
) -> Service:
    (appservers, pingservers, message_servers, api_servers) = [
        [
            Server(
                name=f"landscape-{name}-{sanitize_ip(ip)}-{i}",
                ip=format_ip_for_haproxy(ip),
                port=service_ports[name] + i,
                options=server_options,
            )
            for ip in peer_ips
            for i in range(worker_counts)
        ]
        for name in ("appserver", "pingserver", "message-server", "api")
    ]

    package_upload_servers = [
        Server(
            name="landscape-leader-package-upload",
            ip=format_ip_for_haproxy(leader_ip),
            port=service_ports["package-upload"],
            options=server_options,
        )
    ]

    leader_appservers = [
        Server(
            name=f"landscape-leader-appserver-{i}",
            ip=format_ip_for_haproxy(leader_ip),
            port=service_ports["appserver"] + i,
            options=server_options,
        )
        for i in range(worker_counts)
    ]

    backends = [
        Backend(backend_name=HTTPBackend.APPSERVER, servers=appservers),
        Backend(backend_name=HTTPBackend.PING, servers=pingservers),
        Backend(backend_name=HTTPBackend.MESSAGE, servers=message_servers),
        Backend(backend_name=HTTPBackend.API, servers=api_servers),
        Backend(
            backend_name=HTTPBackend.PACKAGE_UPLOAD, servers=package_upload_servers
        ),
        Backend(backend_name=HTTPBackend.HASHIDS, servers=leader_appservers),
    ]

    return Service(
        frontend=HTTP_FRONTEND,
        backends=backends,
        default_backend=str(HTTPBackend.APPSERVER),
    )


def create_https_service(
    peer_ips: list[IPvAnyAddress],
    leader_ip: IPvAnyAddress,
    worker_counts: int,
    server_options: str = SERVER_OPTIONS,
    service_ports: ServicePorts = SERVICE_PORTS,
) -> Service:
    """
    Create the Landscape HTTPS `services` configurations for HAProxy.

    NOTE: The servers for the package-upload and
    hashid-databases backends are only from the leader unit but
    exist on every unit.
    """
    (appservers, pingservers, message_servers, api_servers) = [
        [
            Server(
                name=f"landscape-{name}-{sanitize_ip(ip)}-{i}",
                ip=format_ip_for_haproxy(ip),
                port=service_ports[name] + i,
                options=server_options,
            )
            for ip in peer_ips
            for i in range(worker_counts)
        ]
        for name in ("appserver", "pingserver", "message-server", "api")
    ]

    package_upload_servers = [
        Server(
            name="landscape-leader-package-upload",
            ip=format_ip_for_haproxy(leader_ip),
            port=service_ports["package-upload"],
            options=server_options,
        )
    ]

    leader_appservers = [
        Server(
            name=f"landscape-leader-appserver-{i}",
            ip=format_ip_for_haproxy(leader_ip),
            port=service_ports["appserver"] + i,
            options=server_options,
        )
        for i in range(worker_counts)
    ]

    backends = [
        Backend(backend_name=HTTPSBackend.APPSERVER, servers=appservers),
        Backend(backend_name=HTTPSBackend.PING, servers=pingservers),
        Backend(backend_name=HTTPSBackend.MESSAGE, servers=message_servers),
        Backend(backend_name=HTTPSBackend.API, servers=api_servers),
        Backend(
            backend_name=HTTPSBackend.PACKAGE_UPLOAD, servers=package_upload_servers
        ),
        Backend(backend_name=HTTPSBackend.HASHIDS, servers=leader_appservers),
    ]

    return Service(
        frontend=HTTPS_FRONTEND,
        backends=backends,
        default_backend=str(HTTPSBackend.APPSERVER),
    )


def create_hostagent_messenger_service(
    peer_ips: list[IPvAnyAddress],
    server_options: str = SERVER_OPTIONS,
    service_ports: dict = SERVICE_PORTS,
) -> Service:
    servers = [
        Server(
            name=f"landscape-hostagent-messenger-{sanitize_ip(ip)}",
            ip=format_ip_for_haproxy(ip),
            port=service_ports["hostagent-messenger"],
            options=f"{GRPC_SERVER_OPTIONS} {server_options}",
        )
        for ip in peer_ips
    ]

    backend = Backend(backend_name=HOSTAGENT_MESSENGER_BACKEND, servers=servers)

    return Service(
        frontend=HOSTAGENT_MESSENGER_FRONTEND,
        backends=[backend],
        default_backend=HOSTAGENT_MESSENGER_BACKEND,
    )


def create_ubuntu_installer_attach_service(
    peer_ips: list[IPvAnyAddress],
    server_options: str = SERVER_OPTIONS,
    service_ports: dict = SERVICE_PORTS,
) -> Service:
    servers = [
        Server(
            name=f"landscape-ubuntu-installer-attach-{sanitize_ip(ip)}",
            ip=format_ip_for_haproxy(ip),
            port=service_ports["ubuntu-installer-attach"],
            options=f"{GRPC_SERVER_OPTIONS} {server_options}",
        )
        for ip in peer_ips
    ]

    backend = Backend(backend_name=UBUNTU_INSTALLER_ATTACH_BACKEND, servers=servers)

    return Service(
        frontend=UBUNTU_INSTALLER_ATTACH_FRONTEND,
        backends=[backend],
        default_backend=UBUNTU_INSTALLER_ATTACH_BACKEND,
    )


def render_config(
    all_ips: list[IPvAnyAddress],
    leader_ip: IPvAnyAddress,
    worker_counts: int,
    redirect_https: RedirectHTTPS,
    enable_hostagent_messenger: bool,
    enable_ubuntu_installer_attach: bool,
    max_connections: int = 4096,
    ssl_cert_path=HAPROXY_CERT_PATH,
    rendered_config_path: str = HAPROXY_RENDERED_CONFIG_PATH,
    service_ports: dict = SERVICE_PORTS,
    error_files_directory=ERROR_FILES["location"],
    error_files=ERROR_FILES["files"],
    server_timeout: int = SERVER_TIMEOUT,
    server_options: str = SERVER_OPTIONS,
    template_path: str = LOCAL_JINJA_TMPL_PATH,
) -> str:
    """Render the HAProxy config with the given context.

    :param all_ips: A list of IP addresses of all peer units
    :param leader_ip: The IP address of the leader unit
    :param worker_counts: The number of worker processes configured
    :param redirect_https: A `RedirectHTTPS` settings to determine how
        to redirect HTTP to HTTPS
    :param enable_hostagent_messenger: Whether to create a frontend/backend for the
        Hostagent Messenger service
    :param enable_ubuntu_installer_attach: Whether to create a frontend/backend for the
        Ubuntu Installer Attach service
    :param max_connections: Maximum concurrent connections for HAProxy,
        defaults to 4096
    :param ssl_cert_path: The path of the SSL certificate to use
        for the HAProxy service, defaults to HAPROXY_CERT_PATH
    :param rendered_config_path: Path where the rendered config will be written,
        defaults to HAPROXY_RENDERED_CONFIG_PATH
    :param service_ports: A mapping of services to their base ports,
        defaults to SERVICE_PORTS
    :param error_files_directory: Directory where the Landscape error files are,
        defaults to ERROR_FILES["location"]
    :param error_files: A mapping of status codes (string) to the name of the
        error file in `error_files_directory`, defaults to ERROR_FILES["files"]
    :param server_timeout: Timeout for backend servers in milliseconds,
        defaults to SERVER_TIMEOUT
    :param server_options: Options for all backend servers,
        defaults to SERVER_OPTIONS
    :param template_path: Path to the Jinja2 template file,
        defaults to LOCAL_JINJA_TMPL_PATH

    :raises HAProxyError: Failed to write the HAProxy configuration file!

    :return rendered: The rendered string given the context.
    """
    redirect_directive = get_redirect_directive(redirect_https)

    http_service = create_http_service(
        peer_ips=all_ips,
        leader_ip=leader_ip,
        worker_counts=worker_counts,
        server_options=server_options,
        service_ports=service_ports,
    )

    https_service = create_https_service(
        peer_ips=all_ips,
        leader_ip=leader_ip,
        worker_counts=worker_counts,
        server_options=server_options,
        service_ports=service_ports,
    )

    hostagent_messenger_service = None
    if enable_hostagent_messenger:
        hostagent_messenger_service = create_hostagent_messenger_service(
            peer_ips=all_ips,
            server_options=server_options,
            service_ports=service_ports,
        )

    ubuntu_installer_attach_service = None
    if enable_ubuntu_installer_attach:
        ubuntu_installer_attach_service = create_ubuntu_installer_attach_service(
            peer_ips=all_ips,
            server_options=server_options,
            service_ports=service_ports,
        )

    env = Environment(
        loader=FileSystemLoader("src"),
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )

    template = env.get_template(template_path)

    context = {
        "ssl_cert_path": ssl_cert_path,
        "redirect_directive": redirect_directive,
        "error_files_directory": error_files_directory,
        "error_files": error_files,
        "global_max_connections": max_connections,
        "server_timeout": server_timeout,
        "http_service": http_service,
        "https_service": https_service,
        "hostagent_messenger_service": hostagent_messenger_service,
        "ubuntu_installer_attach_service": ubuntu_installer_attach_service,
    }

    rendered = template.render(context)

    try:
        write_file(rendered.encode(), rendered_config_path, 0o644)
    except OSError as e:
        raise HAProxyError(f"Failed to write HAProxy config: {str(e)}")

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
    config_path: str = HAPROXY_RENDERED_CONFIG_PATH,
    haproxy_executable=HAPROXY_EXECUTABLE,
    user=HAPROXY_USER,
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
        raise HAProxyError(
            "Failed to validate HAProxy config!"
            f"\nstdout: {str(e.stdout)}\nstderr: {str(e.stderr)}"
        )


def install(package_name: str = HAPROXY_APT_PACKAGE_NAME) -> None:
    """
    Installs the HAProxy apt package locally.

    :raises HAProxyError: Failed to install HAProxy!
    """

    try:
        apt.add_package(package_name, update_cache=True)
    except apt.PackageError as e:
        raise HAProxyError(f"Failed to install HAProxy: {str(e)}")
