from dataclasses import dataclass, field


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


HTTP_SERVICE = Service(
    **{
        "service_name": "landscape-http",
        "service_host": "0.0.0.0",
        "service_port": 80,
        "service_options": [
            "mode http",
            "timeout client 300000",
            "timeout server 300000",
            "balance leastconn",
            "option httpchk HEAD / HTTP/1.0",
            "acl ping path_beg -i /ping",
            "acl repository path_beg -i /repository",
            "use_backend landscape-ping if ping",
            "redirect scheme https unless ping OR repository",
            "acl message path_beg -i /message-system",
            "acl attachment path_beg -i /attachment",
            "acl api path_beg -i /api",
            "acl ping path_beg -i /ping",
            "use_backend landscape-message if message",
            "use_backend landscape-message if attachment",
            "use_backend landscape-api if api",
            "use_backend landscape-ping if ping",
            "acl hashids path_beg -i /hash-id-databases",
            "use_backend landscape-hashid-databases if hashids",
            "acl package-upload path_beg -i /upload",
            "use_backend landscape-package-upload if package-upload",
            "http-request replace-path ^([^\\ ]*)\\ /upload/(.*) /\\1",
            "acl metrics path_end /metrics",
            "http-request deny if metrics",
        ],
    }
)


HTTPS_SERVICE = Service(
    **{
        "service_name": "landscape-https",
        "service_host": "0.0.0.0",
        "service_port": 443,
        "service_options": [
            "mode http",
            "timeout client 300000",
            "timeout server 300000",
            "balance leastconn",
            "option httpchk HEAD / HTTP/1.0",
            "http-request set-header X-Forwarded-Proto https",
            "acl message path_beg -i /message-system",
            "acl attachment path_beg -i /attachment",
            "acl api path_beg -i /api",
            "acl ping path_beg -i /ping",
            "use_backend landscape-message if message",
            "use_backend landscape-message if attachment",
            "use_backend landscape-api if api",
            "use_backend landscape-ping if ping",
            "acl hashids path_beg -i /hash-id-databases",
            "use_backend landscape-hashid-databases if hashids",
            "acl package-upload path_beg -i /upload",
            "use_backend landscape-package-upload if package-upload",
            "http-request replace-path ^([^\\ ]*)\\ /upload/(.*) /\\1",
            "acl metrics path_end /metrics",
            "http-request deny if metrics",
            "acl prometheus_metrics path_beg -i /metrics",
            "http-request deny if prometheus_metrics",
        ],
    }
)

GRPC_SERVICE = Service(
    **{
        "service_name": "landscape-grpc",
        "service_host": "0.0.0.0",
        "service_port": 6554,
        "server_options": ["proto h2"],
    }
)


UBUNTU_INSTALLER_ATTACH_SERVICE = Service(
    **{
        "service_name": "landscape-ubuntu-installer-attach",
        "service_host": "0.0.0.0",
        "service_port": 50051,
        "server_options": ["proto h2"],
        "service_options": [
            "acl host_found hdr(host) -m found",
            "http-request set-var(req.full_fqdn) hdr(authority) if !host_found",
            "http-request set-var(req.full_fqdn) hdr(host) if host_found",
            "http-request set-header X-FQDN %[var(req.full_fqdn)]",
        ],
    }
)


# TODO make immutable
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


# TODO make immutable
PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
    "package-upload": 9100,
    "hostagent-messenger": 50052,
    "ubuntu-installer-attach": 53354,
}


# TODO make immutable
SERVER_OPTIONS = [
    "check",
    "inter 5000",
    "rise 2",
    "fall 5",
    "maxconn 50",
]
