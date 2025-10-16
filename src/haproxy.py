"""
Configuration for the relation between Landscape and HAProxy.
"""

from base64 import b64encode
from dataclasses import asdict, dataclass, field
from enum import Enum
import os
from typing import Iterable, Mapping

from config import RedirectHTTPS


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
    HASHIDS = "landscape-http-hashid-databases"
    MESSAGE = "landscape-http-message"
    PACKAGE_UPLOAD = "landscape-http-package-upload"
    PING = "landscape-http-ping"
    REPOSITORY = "landscape-http-repository"

    def __str__(self) -> str:
        return self.value


class HTTPSBackend(str, Enum):

    API = "landscape-https-api"
    HASHIDS = "landscape-https-hashid-databases"
    MESSAGE = "landscape-https-message"
    PACKAGE_UPLOAD = "landscape-https-package-upload"
    PING = "landscape-https-ping"
    REPOSITORY = "landscape-https-repository"

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Service:
    """
    An HAProxy service configuration.
    """

    service_name: str
    service_host: str
    service_port: int
    server_options: list[str] = field(default_factory=list)
    service_options: list[str] = field(default_factory=list)


DEFAULT_REDIRECT_SCHEME = "redirect scheme https unless ping OR repository"


HTTP_SERVICE = Service(
    service_name="landscape-http",
    service_host="0.0.0.0",
    service_port=80,
    service_options=[
        "mode http",
        "timeout client 300000",
        "timeout server 300000",
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
        # A default for the HTTPS redirect, which is configurable.
        DEFAULT_REDIRECT_SCHEME,
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


HTTPS_SERVICE = Service(
    service_name="landscape-https",
    service_host="0.0.0.0",
    service_port=443,
    service_options=[
        "mode http",
        "timeout client 300000",
        "timeout server 300000",
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

GRPC_SERVICE = Service(
    service_name="landscape-grpc",
    service_host="0.0.0.0",
    service_port=6554,
    server_options=["proto h2"],
)


UBUNTU_INSTALLER_ATTACH_SERVICE = Service(
    service_name="landscape-ubuntu-installer-attach",
    service_host="0.0.0.0",
    service_port=50051,
    server_options=["proto h2"],
    service_options=[
        # The X-FQDN header is required for multitenant installations
        "acl host_found hdr(host) -m found",
        "http-request set-var(req.full_fqdn) hdr(authority) if !host_found",
        "http-request set-var(req.full_fqdn) hdr(host) if host_found",
        "http-request set-header X-FQDN %[var(req.full_fqdn)]",
    ],
)


ERROR_FILES = {
    "location": "/opt/canonical/landscape/canonical/landscape/offline",
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


SERVER_OPTIONS = [
    "check",
    "inter 5000",
    "rise 2",
    "fall 5",
    "maxconn 50",
]


@dataclass
class HAProxyErrorFile:
    """
    Configuration for HAProxy error files
    """

    http_status: int
    """The status code the error file should handle."""
    content: bytes
    """The b64-encoded content of the error file."""


HAProxyServicePorts = Mapping[str, int]
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
HAProxyServerOptions = list[str]
"""
Additional configuration for a `server` stanza in an HAProxy configuration.
"""


# NOTE: See https://charmhub.io/haproxy/configurations#services for details on
# the format of HAProxy service configurations.


def create_http_service(
    http_service: dict,
    server_ip: str,
    unit_name: str,
    worker_counts: int,
    is_leader: bool,
    error_files: Iterable["HAProxyErrorFile"],
    service_ports: "HAProxyServicePorts",
    server_options: "HAProxyServerOptions",
    redirect_https: RedirectHTTPS | None = None,
) -> dict:
    """
    Create the Landscape HTTP `services` configurations for HAProxy.

    NOTE: Only the leader should have servers for the package-upload and
    hashid-databases backends. However, when the leader is lost, haproxy will fail as
    the service options will reference a (no longer) existing backend. To prevent that,
    all units should declare all backends, even if a unit should not have any servers on
    a specific backend.
    """
    (appservers, pingservers, message_servers, api_servers) = [
        [
            (
                f"landscape-{name}-{unit_name}-{i}",
                server_ip,
                service_ports[name] + i,
                server_options,
            )
            for i in range(worker_counts)
        ]
        for name in ("appserver", "pingserver", "message-server", "api")
    ]

    package_upload_servers = [
        (
            f"landscape-package-upload-{unit_name}-0",
            server_ip,
            service_ports["package-upload"],
            server_options,
        )
    ]

    http_service["servers"] = appservers
    http_service["backends"] = [
        {
            "backend_name": "landscape-http-ping",
            "servers": pingservers,
        },
        {
            "backend_name": "landscape-http-message",
            "servers": message_servers,
        },
        {
            "backend_name": "landscape-http-api",
            "servers": api_servers,
        },
        {
            "backend_name": "landscape-http-package-upload",
            "servers": package_upload_servers if is_leader else [],
        },
        {
            "backend_name": "landscape-http-hashid-databases",
            "servers": appservers if is_leader else [],
        },
    ]

    http_service["error_files"] = [asdict(ef) for ef in error_files]

    if redirect_https:
        _configure_redirect_https(http_service, redirect_https)

    return http_service


def _configure_redirect_https(
    http_service: dict,
    redirect_https: RedirectHTTPS,
    marker_stanza: str = DEFAULT_REDIRECT_SCHEME,
) -> dict:
    """
    Configure the HTTP routes that should redirect to HTTPS.

    Requires the presence of a `marker_stanza` in the `http_service` to
    identify the stanza to reconfigure.
    """
    match redirect_https:
        case RedirectHTTPS.ALL:
            stanza = "redirect scheme https"
        case RedirectHTTPS.NONE:
            stanza = "# No HTTPS redirect"  # use an HAProxy comment for 'no redirect'
        case RedirectHTTPS.DEFAULT:
            stanza = DEFAULT_REDIRECT_SCHEME

    try:
        index = http_service["service_options"].index(marker_stanza)
    except ValueError:
        raise Exception(
            f"No '{marker_stanza}' found in service; cannot configure redirect."
        )

    http_service["service_options"][index] = stanza

    return http_service


def create_https_service(
    https_service: dict,
    ssl_cert: bytes | str,
    server_ip: str,
    unit_name: str,
    worker_counts: int,
    is_leader: bool,
    error_files: Iterable["HAProxyErrorFile"],
    service_ports: "HAProxyServicePorts",
    server_options: "HAProxyServerOptions",
) -> dict:
    """
    Create the Landscape HTTPS `services` configurations for HAProxy.

    NOTE: Only the leader should have servers for the package-upload and
    hashid-databases backends. However, when the leader is lost, haproxy will fail as
    the service options will reference a (no longer) existing backend. To prevent that,
    all units should declare all backends, even if a unit should not have any servers on
    a specific backend.
    """
    (appservers, pingservers, message_servers, api_servers) = [
        [
            (
                f"landscape-{name}-{unit_name}-{i}",
                server_ip,
                service_ports[name] + i,
                server_options,
            )
            for i in range(worker_counts)
        ]
        for name in ("appserver", "pingserver", "message-server", "api")
    ]

    package_upload_servers = [
        (
            f"landscape-package-upload-{unit_name}-0",
            server_ip,
            service_ports["package-upload"],
            server_options,
        )
    ]

    https_service["servers"] = appservers
    https_service["backends"] = [
        {
            "backend_name": "landscape-https-ping",
            "servers": pingservers,
        },
        {
            "backend_name": "landscape-https-message",
            "servers": message_servers,
        },
        {
            "backend_name": "landscape-https-api",
            "servers": api_servers,
        },
        {
            "backend_name": "landscape-https-package-upload",
            "servers": package_upload_servers if is_leader else [],
        },
        {
            "backend_name": "landscape-https-hashid-databases",
            "servers": appservers if is_leader else [],
        },
    ]

    https_service["error_files"] = [asdict(ef) for ef in error_files]
    https_service["crts"] = [ssl_cert]
    return https_service


def create_grpc_service(
    grpc_service: dict,
    ssl_cert: bytes | str,
    server_ip: str,
    unit_name: str,
    error_files: Iterable["HAProxyErrorFile"],
    service_ports: "HAProxyServicePorts",
    server_options: "HAProxyServerOptions",
) -> dict:
    """
    Create the Landscape WSL hostagent `services` configuration for HAProxy.
    """

    grpc_service["crts"] = [ssl_cert]
    hostagent_messenger = [
        (
            f"landscape-hostagent-messenger-{unit_name}-0",
            server_ip,
            service_ports["hostagent-messenger"],
            server_options + grpc_service["server_options"],
        )
    ]
    grpc_service["servers"] = hostagent_messenger
    grpc_service["error_files"] = [asdict(ef) for ef in error_files]

    return grpc_service


def create_ubuntu_installer_attach_service(
    ubuntu_installer_attach_service: dict,
    ssl_cert: bytes | str,
    server_ip: str,
    unit_name: str,
    error_files: Iterable["HAProxyErrorFile"],
    service_ports: "HAProxyServicePorts",
    server_options: "HAProxyServerOptions",
) -> dict:
    """
    Create the Landscape Ubuntu installer attach `services` configuration for HAProxy.
    """

    ubuntu_installer_attach_service["crts"] = [ssl_cert]
    ubuntu_installer_attach_server = [
        (
            f"landscape-ubuntu-installer-attach-{unit_name}-0",
            server_ip,
            service_ports["ubuntu-installer-attach"],
            server_options + ubuntu_installer_attach_service["server_options"],
        )
    ]
    ubuntu_installer_attach_service["servers"] = ubuntu_installer_attach_server
    ubuntu_installer_attach_service["error_files"] = [asdict(ef) for ef in error_files]

    return ubuntu_installer_attach_service


def get_haproxy_error_files(error_files_config: dict) -> list[HAProxyErrorFile]:
    error_files_location = error_files_config["location"]
    error_files = []
    for code, filename in error_files_config["files"].items():
        error_file_path = os.path.join(error_files_location, filename)
        with open(error_file_path, "rb") as error_file:
            error_files.append(
                HAProxyErrorFile(
                    http_status=code,
                    content=b64encode(error_file.read()),
                )
            )

    return error_files
