

|  |  |  |  |
| :---- | :---- | :---- | :---- |
| Title | Migrating away from the legacy HAProxy charm |  |  |
| **[Type](https://docs.google.com/document/d/1lStJjBGW7lyojgBhxGLUNnliUocYWjAZ1VEbbVduX54/edit?usp=sharing)** | **Author(s)** | **[Status](https://docs.google.com/document/d/1lStJjBGW7lyojgBhxGLUNnliUocYWjAZ1VEbbVduX54/edit?usp=sharing)** | **Created** |
| Implementation | [Jan-Yaeger Dhillon](mailto:jan.dhillon@canonical.com) | Pending Review | 28 Nov 2025 |
|  | **Reviewer(s)** | **Status** | **Date** |
|  | [Mitch Burton](mailto:mitch.burton@canonical.com) | Approved | 8 Jan 2026 |

# Abstract

The Landscape Server charm is migrating away from the legacy HAProxy charm in favor of installing HAProxy on each Landscape Server unit.

# Rationale

The Landscape SaaS environments are migrating from PS5 to PS7 and we need to make our deployment compatible with the ingress requirements by making the charm compatible with the Ingress Configurator charm. This also gives us the opportunity to remove the Landscape Server charm’s dependency on the HAProxy charm specifically and will make it easier to customize the load balancing for Landscape.

# Specification

## Legacy HAProxy charm

### **Defining frontends, routes, and backends**

The Landscape Server charm uses HAProxy as its load balancer via the  `website` relation. Historically, this [meant that Landscape directly told HAproxy what “services” to create](https://github.com/canonical/landscape-charm/blob/89e5e96c6a91c323e781d5322ece223079d41de6/src/haproxy.py), which is what the legacy HAproxy used to refer to a frontend with specification path and backend definitions. That is, we are putting the frontend, backend, and routing definitions directly in the charm code. Additionally, Landscape Server would not start the services until HAProxy was available. There are four services created by the legacy Landscape Server charm: the HTTP service, the HTTPS service, the hostagent messenger service, and the Ubuntu installer attach service. Notably, we created separate frontends for each frontend port/protocol combination, meaning we also had double the number of backends for the non-gRPC services:

```py
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
```

#### Key Info

| Service | Frontend port | Paths | Backend | Additional options |
| :---- | :---- | :---- | :---- | :---- |
| HTTP | 80 | `/ping` | Pingserver | Client timeout: 300,000ms (300s) Server timeout: 300,000ms (300s) Load balancing algorithm: `leastconn` HTTPs redirects: By default, all except ACLs except `/ping` and `/repository` will redirect to HTTPS Path rewrite expressions: If the path contains a space followed by `/upload/`, delete the space, delete `/upload/`, and delete the filename, keeping only what was before the space. |
|  |  | `/api` | API server |  |
|  |  | `/repository`, `/hash-id-databases` | Appserver |  |
|  |  | `/upload` | Package upload |  |
|  |  | `/message-system`, `/attachment` | Message server |  |
|  |  | `/metrics` | Blocked (ports are scraped by COS and not exposed by HAProxy) |  |
| HTTPS | 443 | `/ping` | Pingserver | Client timeout: 300,000ms (300s) Server timeout: 300,000ms (300s) Load balancing algorithm: `leastconn` Path rewrite expressions: If the path contains a space followed by `/upload/`, delete the space, delete `/upload/`, and delete the filename, keeping only what was before the space. |
|  |  | `/api` | API server |  |
|  |  | `/repository`, `/`, `/hash-id-databases` | Appserver |  |
|  |  | `/upload` | Package upload |  |
|  |  | `/message-system`, `/attachment` | Message server |  |
|  |  | `/metrics` | Blocked (ports are scraped by COS and not exposed by HAProxy) |  |
| gRPC (hostagent messenger) Service | 6554 | None | Hostagent messenger | Only listens on HTTP/2 (no ALPN) |
| Ubuntu Installer Attach Service | 50051 | None | Ubuntu installer attach service | Only listens on HTTP/2 (no ALPN) Header rewrite rule: Read the `Host` or `Authority` field and copy it into `X-FQDN` |

Additionally, the default backend would be set to appserver in the generated HAProxy config:

```json
frontend haproxy-0-443
    bind 0.0.0.0:443 ssl crt /var/lib/haproxy/default.pem no-sslv3
    default_backend landscape-https

backend landscape-https
    mode http
    timeout server 300000
    balance leastconn
    option httpchk HEAD / HTTP/1.0
    server landscape-appserver-landscape-server-0-0 10.21.66.24:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-landscape-server-0-1 10.21.66.24:8081 check inter 5000 rise 2 fall 5 maxconn 50

```

This means that all traffic directed at port 80 or 443 of the IP address of the HAProxy charm that did not match another ACL in the frontend would be redirected to the appserver backend.

Additionally, Twisted services can spawn multiple worker processes with distinct ports, so there is logic to dynamically add a server entry to the HAProxy config for each worker process:

```py
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
```

   
Note that certain backends are only created for leader units.

### **Storing the root URL using HAProxy’s hostname/IP**

In the legacy implementation, the relation between Landscape Server and HAProxy is directly read to extract HAProxy’s public address and written to several sections in the `service.conf` using the following:

```py
url = f'https://{event.relation.data[event.unit]["public-address"]}/'
self._stored.default_root_url = url
update_service_conf(
    {
        "global": {"root-url": url},
        "api": {"root-url": url},
        "package-upload": {"root-url": url},
    }
)
```

### **TLS**

TLS termination happens at the load balancer level and traffic is passed to Landscape Server backends as unencrypted HTTP. The legacy HAProxy charm has config options to set TLS certificates and create self-signed ones, and the Landscape Server charm will [verify the validity of combinations of SSL credentials](https://github.com/canonical/landscape-charm/blob/89e5e96c6a91c323e781d5322ece223079d41de6/src/charm.py#L190) and [use the credentials to create the services](https://github.com/canonical/landscape-charm/blob/89e5e96c6a91c323e781d5322ece223079d41de6/src/charm.py#L1088). 

## Installing HAProxy in the Landscape Server Charm

To migrate away from the legacy HAProxy charm, we are opting to install HAProxy manually alongside Landscape Server on each unit, and then configuring the service to dynamically route traffic to the peer units of the Landscape Server charm. For example, a non-leader unit will still route traffic from `/upload` to the leader unit’s package upload server. We can use the `replicas` relation to extract the peer and leader unit IP addresses to template the HAProxy config. Historically, the HAProxy charm constructed the configuration almost entirely manually using Python. However, they’ve since [opted to use Jinja templates](https://github.com/canonical/haproxy-operator/tree/main/haproxy-operator/templates), which significantly reduces the amount of code needed to create the config file, and we should opt to take a similar approach. Additionally, we will remove the `website` relation endpoint that was used by the legacy HAProxy charm, fully dropping support for it. 

This approach grants us full control over the HAProxy configuration and allows us to add things like custom error files. It also allows us to easily put another load balancer in front of Landscape Server, either manually (ex. public cloud) or via the new `ingress` relations, which use the [`IngressPerAppRequirer` charm library](https://github.com/canonical/ingress-configurator-operator/blob/main/lib/charms/traefik_k8s/v2/ingress.py) to automatically scrape the related Landscape Server unit addresses and store them in the relation, which can then be forwarded via the `haproxy-route` interface to a remote HAProxy charm by integrating with a remote offer. This is a [requirement for deployments on Prodstack 7](https://canonical-information-systems-documentation.readthedocs-hosted.com/en/latest/how-to/ps7-developer-onboarding/#ingress-networking), which is where we plan to migrate our production environments to.  
   
A working example can be found in [this pull request](https://github.com/canonical/landscape-charm/pull/38).

### **Creating the backends**

We can modify our legacy HAProxy module to create similar structured data representing our frontends, backends, and options, but without the external restrictions (it no longer needs to be a raw dictionary with specific keys):

```py
# haproxy.py

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

    APPSERVER = "landscape-http-appserver"
    API = "landscape-http-api"
    HASHIDS = "landscape-http-hashid-databases"
    MESSAGE = "landscape-http-message"
    PACKAGE_UPLOAD = "landscape-http-package-upload"
    PING = "landscape-http-ping"

    def __str__(self) -> str:
        return self.value


class HTTPSBackend(str, Enum):
    """HTTPS backend identifiers."""

    APPSERVER = "landscape-https-appserver"
    API = "landscape-https-api"
    HASHIDS = "landscape-https-hashid-databases"
    MESSAGE = "landscape-https-message"
    PACKAGE_UPLOAD = "landscape-https-package-upload"
    PING = "landscape-https-ping"

    def __str__(self) -> str:
        return self.value


HOSTAGENT_MESSENGER_BACKEND = "landscape-hostagent-messenger"
UBUNTU_INSTALLER_ATTACH_BACKEND = "landscape-ubuntu-installer-attach"


class FrontendName(str, Enum):
    HTTP = "landscape-http"
    HTTPS = "landscape-https"
    HOSTAGENT_MESSENGER = "landscape-hostagent-messenger"
    UBUNTU_INSTALLER_ATTACH = "landscape-ubuntu-installer-attach"

    def __str__(self) -> str:
        return self.value


class FrontendPort(int, Enum):
    HTTP = 80
    HTTPS = 443
    HOSTAGENT_MESSENGER = 6554
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


CLIENT_TIMEOUT = 300000  # ms
SERVER_TIMEOUT = 300000  # ms
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

def create_http_service(
    frontend: Frontend,
    peer_ips: list[IPvAnyAddress],
    leader_ip: IPvAnyAddress,
    worker_counts: int,
    server_options: str = DEFAULT_SERVER_OPTIONS,
    service_ports: dict = SERVICE_PORTS,
) -> Service:
    (appservers, pingservers, message_servers, api_servers) = [
        [
            Server(
                name=f"landscape-{name}-{str(ip).replace('.', '-')}-{i}",
                ip=str(ip),
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
            name=f"landscape-package-upload-{str(leader_ip).replace('.', '-')}-0",
            ip=str(leader_ip),
            port=service_ports["package-upload"],
            options=server_options,
        )
    ]

    leader_appservers = [
        Server(
            name=f"landscape-appserver-{str(leader_ip).replace('.', '-')}-{i}",
            ip=str(leader_ip),
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
        frontend=frontend,
        backends=backends,
        default_backend=str(HTTPBackend.APPSERVER),
    )


def create_https_service(
    frontend: Frontend,
    peer_ips: list[IPvAnyAddress],
    leader_ip: IPvAnyAddress,
    worker_counts: int,
    server_options: str = DEFAULT_SERVER_OPTIONS,
    service_ports: dict = SERVICE_PORTS,
) -> Service:
    (appservers, pingservers, message_servers, api_servers) = [
        [
            Server(
                name=f"landscape-{name}-{str(ip).replace('.', '-')}-{i}",
                ip=str(ip),
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
            name=f"landscape-package-upload-{str(leader_ip).replace('.', '-')}-0",
            ip=str(leader_ip),
            port=service_ports["package-upload"],
            options=server_options,
        )
    ]

    leader_appservers = [
        Server(
            name=f"landscape-appserver-{str(leader_ip).replace('.', '-')}-{i}",
            ip=str(leader_ip),
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
        frontend=frontend,
        backends=backends,
        default_backend=str(HTTPSBackend.APPSERVER),
    )


def create_hostagent_messenger_service(
    frontend: Frontend,
    peer_ips: list[IPvAnyAddress],
    server_options: str = DEFAULT_SERVER_OPTIONS,
    service_ports: dict = SERVICE_PORTS,
) -> Service:
    servers = [
        Server(
            name=f"hostagent-{str(ip).replace('.', '-')}-0",
            ip=str(ip),
            port=service_ports["hostagent-messenger"],
            options=f"{GRPC_SERVER_OPTIONS} {server_options}",
        )
        for ip in peer_ips
    ]

    backend = Backend(backend_name=HOSTAGENT_MESSENGER_BACKEND, servers=servers)

    return Service(
        frontend=frontend,
        backends=[backend],
        default_backend=HOSTAGENT_MESSENGER_BACKEND,
    )


def create_ubuntu_installer_attach_service(
    frontend: Frontend,
    peer_ips: list[IPvAnyAddress],
    server_options: str = DEFAULT_SERVER_OPTIONS,
    service_ports: dict = SERVICE_PORTS,
) -> Service:
    servers = [
        Server(
            name=f"ubuntu-installer-attach-{str(ip).replace('.', '-')}-0",
            ip=str(ip),
            port=service_ports["ubuntu-installer-attach"],
            options=f"{GRPC_SERVER_OPTIONS} {server_options}",
        )
        for ip in peer_ips
    ]

    backend = Backend(backend_name=UBUNTU_INSTALLER_ATTACH_BACKEND, servers=servers)

    return Service(
        frontend=frontend,
        backends=[backend],
        default_backend=UBUNTU_INSTALLER_ATTACH_BACKEND,
    )
```

We can then pass these `Service` definitions to the Jinja template to dynamically create the HAProxy configuration file. 

We should also add a maximum global HAProxy connection config option to our charm, [similar to the HAProxy charm](https://charmhub.io/haproxy/configurations?channel=2.8/edge#global-maxconn):

```json
max_global_haproxy_connections:
  type: int
  default: 4096
  description: |
    Maximum number of concurrent connections HAProxy will accept globally across all
    frontends and backends. This sets the 'maxconn' value in the global section of
    the HAProxy configuration.
```

### **Example Jinja template**

We can achieve similar results to our legacy approach using a Jinja template like the following:

```json

global
    maxconn {{ global_max_connections }}
    user haproxy
    group haproxy

    log /dev/log local0

    # generated 2026-01-07, Mozilla Guideline v5.7, HAProxy 2.8, OpenSSL 1.1.1w (UNSUPPORTED; end-of-life), intermediate config, no HSTS
    # https://ssl-config.mozilla.org/#server=haproxy&version=2.8&config=intermediate&openssl=1.1.1w&hsts=false&guideline=5.7
    # intermediate configuration
    ssl-default-bind-curves X25519:prime256v1:secp384r1
    ssl-default-bind-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305
    ssl-default-bind-ciphersuites TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256
    ssl-default-bind-options prefer-client-ciphers ssl-min-ver TLSv1.2 no-tls-tickets

    ssl-default-server-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305
    ssl-default-server-ciphersuites TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256
    ssl-default-server-options ssl-min-ver TLSv1.2 no-tls-tickets

    tune.ssl.default-dh-param 2048

defaults
    log global
    mode http
    option httplog
    option dontlognull
    retries 3
    timeout queue 60000
    timeout connect 5000
    timeout client 120000
    timeout server 120000

{% for status, filename in error_files.items() %}
    errorfile {{ status }} {{ error_files_directory }}/{{ filename }}
{% endfor %}

frontend {{ http_service.frontend.frontend_name }}
    bind [::]:{{ http_service.frontend.frontend_port }} v4v6
{% for option in http_service.frontend.frontend_options %}
    {{ option }}
{% endfor %}

    {% if redirect_directive %}
    {{ redirect_directive }}
    {% endif %}

    default_backend {{ http_service.default_backend }}

frontend {{ https_service.frontend.frontend_name }}
    bind [::]:{{ https_service.frontend.frontend_port }} v4v6 ssl crt {{ ssl_cert_path }}
{% for option in https_service.frontend.frontend_options %}
    {{ option }}
{% endfor %}

    default_backend {{ https_service.default_backend }}

{% if hostagent_messenger_service %}
frontend {{ hostagent_messenger_service.frontend.frontend_name }}
    bind [::]:{{ hostagent_messenger_service.frontend.frontend_port }} v4v6 ssl crt {{ ssl_cert_path }} alpn h2,http/1.1
{% for option in hostagent_messenger_service.frontend.frontend_options %}
    {{ option }}
{% endfor %}

    default_backend {{ hostagent_messenger_service.default_backend }}
{% endif %}

{% if ubuntu_installer_attach_service %}
frontend {{ ubuntu_installer_attach_service.frontend.frontend_name }}
    bind [::]:{{ ubuntu_installer_attach_service.frontend.frontend_port }} v4v6 ssl crt {{ ssl_cert_path }} alpn h2,http/1.1
{% for option in ubuntu_installer_attach_service.frontend.frontend_options %}
    {{ option }}
{% endfor %}

    default_backend {{ ubuntu_installer_attach_service.default_backend }}
{% endif %}

{% for backend in http_service.backends %}
backend {{ backend.backend_name }}
    mode http
    timeout server {{ server_timeout }}
    {% for server in backend.servers %}
    server {{ server.name }} {{ server.ip }}:{{ server.port }} {{ server.options }}
    {% endfor %}

{% endfor %}

{% for backend in https_service.backends %}
backend {{ backend.backend_name }}
    mode http
    timeout server {{ server_timeout }}
    {% for server in backend.servers %}
    server {{ server.name }} {{ server.ip }}:{{ server.port }} {{ server.options }}
    {% endfor %}

{% endfor %}

{% if hostagent_messenger_service %}
{% for backend in hostagent_messenger_service.backends %}
backend {{ backend.backend_name }}
    mode http
    timeout server {{ server_timeout }}
    {% for server in backend.servers %}
    server {{ server.name }} {{ server.ip }}:{{ server.port }} {{ server.options }}
    {% endfor %}

{% endfor %}
{% endif %}

{% if ubuntu_installer_attach_service %}
{% for backend in ubuntu_installer_attach_service.backends %}
backend {{ backend.backend_name }}
    mode http
    timeout server {{ server_timeout }}
    {% for server in backend.servers %}
    server {{ server.name }} {{ server.ip }}:{{ server.port }} {{ server.options }}
    {% endfor %}

{% endfor %}
{% endif %}
```

### **Rendering the template and managing the internal HAProxy service**

We can modify our `haproxy.py` module to render the Jinja template and provide helpers for handling the internal HAProxy service:

```py
# haproxy.py
from enum import Enum
import os
from pathlib import Path
import pwd
import subprocess
from subprocess import CalledProcessError

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
HAPROXY_TMPL = Path("haproxy.cfg.j2")


class HAProxyError(Exception):
    """
    Errors raised when interacting with the local HAProxy service.
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

    try:
        for filename in error_files_config.get("files", {}).values():
            src_file = os.path.join(src_dir, filename)
            dst_file = os.path.join(dst_dir, filename)
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
    template_path: Path = HAPROXY_TMPL,
) -> str:
    """Render the HAProxy config with the given context.

    :param all_ips: A list of IP addresses of all peer units
    :param leader_ip: The IP address of the leader unit
    :param worker_counts: The number of worker processes configured
    :param redirect_https: Whether to redirect HTTP to HTTPS
    :param enable_hostagent_messenger: Whether to create a frontend/backend for the hostagent messenger service
    :param enable_ubuntu_installer_attach: Whether to create a frontend/backend for the Ubuntu Installer Attach service
    :param max_connections: Maximum concurrent connections for HAProxy, defaults to 4096
    :param ssl_cert_path: The path of the SSL certificate to use for the HAProxy service,
        defaults to HAPROXY_CERT_PATH
    :param rendered_config_path: Path where the rendered config will be written, defaults to HAPROXY_RENDERED_CONFIG_PATH
    :param service_ports: A mapping of services to their base ports, defaults to SERVICE_PORTS
    :param error_files_directory: Directory where the Landscape error files are, defaults
        to ERROR_FILES["location"]
    :param error_files: A mapping of status codes (string) to the name of the error file in
        `error_files_directory`, defaults to ERROR_FILES["files"]
    :param server_timeout: Timeout for backend servers in milliseconds, defaults to SERVER_TIMEOUT
    :param server_options: Options for all backend servers, defaults to SERVER_OPTIONS
    :param template_path: Path to the Jinja2 template file, defaults to HAPROXY_TMPL

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
            f"Failed to validate HAProxy config! \nstdout: {str(e.stdout)}\nstderr: {str(e.stderr)}"
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
```

A lot of this is based on [how the new HAProxy charm handles similar operations and renders the Jinja template](https://github.com/canonical/haproxy-operator/blob/main/haproxy-operator/src/haproxy.py).

### **Handling in Landscape Server Charm**

#### On Install

In the `_on_install`  hook, we need to first install HAProxy:

```py
try:
    haproxy.install()
except haproxy.HAProxyError as e:
    logger.error("Failed to install HAProxy: %s", str(e))
    raise e
```

Then, copy Landscape’s error files to the HAProxy error directory:

```py
LANDSCAPE_ERROR_FILES_DIR = "/opt/canonical/landscape/canonical/landscape/offline"

...

# Copy Landscape's error files to HAProxy error dir
try:
    haproxy.copy_error_files_from_source(LANDSCAPE_ERROR_FILES_DIR)
except haproxy.HAProxyError as e:
    logger.error("Failed to copy error files: %s", str(e))
raise e

self.unit.status = ActiveStatus("Unit is ready")
```

#### Peer IPs

Because the Landscape Server charm needs to be aware of the IP addresses of its units and the leader unit, we use helpers to retrieve this data from the `replicas` relation in the model:

```py

class PeerIPs(BaseModel):
    all_ips: list[IPvAnyAddress]
    leader_ip: IPvAnyAddress

...

@property
def peer_ips(self) -> PeerIPs | None:
    unit_ip = self.unit_ip
    if not unit_ip:
        return None

    all_ips = [unit_ip]
    leader_ip = unit_ip

    logger.debug(f"replicas: {self.model.get_relation('replicas').data}")
    if replicas := self.model.get_relation("replicas"):
        leader_ip = replicas.data[self.app].get("leader-ip", unit_ip)

        for unit in replicas.units:
            if unit != self.unit:
                if peer_unit_address := replicas.data[unit].get("private-address"):
                    all_ips.append(peer_unit_address)

    peer_ips = PeerIPs(all_ips=all_ips, leader_ip=leader_ip)

    return peer_ips

@property
def unit_ip(self) -> str | None:
    network_binding = self.model.get_binding("replicas")
    if network_binding is None:
        return None

    try:
        bind_address = network_binding.network.bind_address
    except ModelError as e:
        logger.warning(f"No bind address found for `replics`: {str(e)}")
        return None

    if bind_address is not None:
        return str(bind_address)

    return None
```

 

#### TLS Credentials for HAProxy

Previously, we were relying on the HAProxy charm to generate a self-signed TLS certificate for us if the charm’s `ssl_cert` config value was set to `DEFAULT`. Now that we are installing HAProxy in the units directly, we need another way to pass existing TLS certificates to HAProxy and generated self-signed ones. While we could implement generating a self-signed certificate in our own charm, it would introduce a lot of complexity around managing the per-unit CA and we would essentially be creating a bespoke version of the [TLSRequires charm library](https://pypi.org/project/charmlibs-interfaces-tls-certificates/), so we should just use that instead by exposing a new `requires` endpoint that uses the `tls-certificates` interface:

```json
load-balancer-certificates:
    interface: tls-certificates
    limit: 1
```

Now, we can use the charm library to request per-unit TLS certificates:

```py
self.lb_certificates = TLSCertificatesRequiresV4(
    charm=self,
    relationship_name="load-balancer-certificates",
    certificate_requests=(
        [self._get_certificate_request_attributes()]
        if self._get_certificate_request_attributes()
        else []
    ),
    mode=Mode.UNIT,
    refresh_events=[
        self.on.config_changed,
        self.on.replicas_relation_changed,
        self.on.replicas_relation_joined,
        self.on.leader_elected,
        self.on.leader_settings_changed,
    ],
)
```

Note that we are setting the `refresh_events` to the hooks related to the config, peer relation, or leadership changing to ensure HAProxy has the most up-to-date Certificate Signing Requests when it attempts to retrieve its TLS certificate using `_get_certificate_request_attributes`:

```py
def _get_certificate_request_attributes(
        self,
    ) -> CertificateRequestAttributes | None:
    unit_ip = self.unit_ip
    if not unit_ip:
        return None

    hostname = None
    if self.charm_config.root_url:
        parsed = urlparse(self.charm_config.root_url)
        if parsed.hostname:
            hostname = parsed.hostname

    common_name = hostname or unit_ip

    if hostname:
        return CertificateRequestAttributes(
            common_name=common_name,
            sans_ip=[unit_ip],
            sans_dns=[hostname],
        )

    else:
        return CertificateRequestAttributes(
            common_name=unit_ip,
            sans_ip=[unit_ip],
        )
```

The common name is required, which will be the hostname from the `root_url` config option, if provided, or the unit’s IP address. If the hostname is present, it will also be set in the subject alternative name as the DNS, which allows the Landscape Server units to be reachable over TLS by that hostname if added to the trust store. In both cases, the IP address of the unit is used to request the certificate and set as the IP address in the subject alternate name.

Each unit should have its own TLS certificate since they will each use it for their HAProxy configuration and have distinct addresses, however this approach offloading the complex per-unit certificate and private key managing to the `tls-certificates` charm library:

```py
class LandscapeServerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        ...
        # Make sure the charm waits on this relation as well
        self._stored.set_default(
            ready={
                "db": False,
                "inbound-amqp": False,
                "outbound-amqp": False,
                "load-balancer-certificates": False,
            }
        )

...

def _update_haproxy(self) -> None:
    peer_ips = self.peer_ips

    if not peer_ips:
        logger.warning("Peer IPs not set, not updating HAProxy config.")
        return

    cert_attrs = self._get_certificate_request_attributes()
    if not cert_attrs:
        logger.warning("Unable to generate certificate request attributes.")
        return

    provider_certificate, private_key = (
        self.lb_certificates.get_assigned_certificate(
            certificate_request=cert_attrs
        )
    )

    if not provider_certificate or not private_key:
        self.unit.status = WaitingStatus(
            "Waiting for load balancer TLS certificate..."
        )
        logger.warning(
            "Certificate or private key is not yet available! "
            "Make sure this charm has been integrated with a "
            "provider of the `tls-certificates` charm interface."
        )
        self._update_ready_status()
        return

    self._stored.ready["load-balancer-certificates"] = True
    

    ... 
```

Because we are doing TLS termination at the level of each internal HAProxy, as well as at a potential higher-level load balancer, we need to create a Juju action to retrieve the certificates (based on [how the new HAProxy charm handles this](https://github.com/canonical/haproxy-operator/blob/d71ca6c0f88d47bd644dde5aa222b88d279ed020/haproxy-operator/src/charm.py#L219)):

```py
def _on_get_certificates_action(self, event: ActionEvent) -> None:
    cert_attrs = self._get_certificate_request_attributes()
    if not cert_attrs:
        event.fail("TLS certificate not available!")
        return

    provider_certificate, _ = self.lb_certificates.get_assigned_certificate(
        certificate_request=cert_attrs
    )

    event.set_results(
        {
            "certificate": str(provider_certificate.certificate),
            "ca": str(provider_certificate.ca),
            "chain": "\n\n".join([str(cert) for cert in provider_certificate.chain]),
        }
    )
```

Then, the CA certificate can be extracted from the results, which can be added to the trust store of an external load balancer, for example:

```shell
juju run landscape-server/0 get-certificates --format=json | jq -r '.["landscape-server/0"].["results"].["ca"]'
```

This also means we will remove the legacy `ssl_cert` and `ssl_key` config options and instruct users to deploy a provider of the `tls-certificates` charm interface (ex. `self-signed-certificates` charm) in the migration guide.

#### Updating the HAProxy config on the units

We can combine the previous methods from the Landscape Server charm as well as the helpers from the HAProxy module and the TLS certificates charm library to dynamically render the HAProxy configuration on each unit:

```py
def _update_haproxy(self) -> None:
    
    ...

    # Update root_url, if not provided.
    if not self.charm_config.root_url:
        url = f"https://{peer_ips.leader_ip}/"
        self._stored.default_root_url = url
        update_service_conf(
            {
                "global": {"root-url": url},
                "api": {"root-url": url},
                "package-upload": {"root-url": url},
            }
        )

    try:
        haproxy.write_tls_cert(
            provider_certificate=provider_certificate, private_key=private_key
        )

    except haproxy.HAProxyError as e:
        logger.error("Failed to write TLS certificate for HAProxy: %s", str(e))
        self.unit.status = BlockedStatus(
            "Failed to write TLS certificate for HAProxy!"
        )
        return

    try:
        haproxy.render_config(
            all_ips=peer_ips.all_ips,
            leader_ip=peer_ips.leader_ip,
            worker_counts=self.charm_config.worker_counts,
            redirect_https=self.charm_config.redirect_https,
            enable_hostagent_messenger=self.charm_config.enable_hostagent_messenger,
            enable_ubuntu_installer_attach=self._stored.enable_ubuntu_installer_attach,
            max_connections=self.charm_config.max_global_haproxy_connections,
        )

    except haproxy.HAProxyError as e:
        logger.error("Failed to write HAProxy config: %s", str(e))
        self.unit.status = BlockedStatus("Failed to update HAProxy config!")
        return

    try:
        haproxy.validate_config()
    except haproxy.HAProxyError as e:
        logger.error("Failed to validate HAProxy config: %s", str(e))
        self.unit.status = BlockedStatus("Failed to update HAProxy config!")
        return

    try:
        haproxy.reload()
    except haproxy.HAProxyError as e:
        logger.error("Failed to reload HAProxy: %s", str(e))
        self.unit.status = BlockedStatus("Failed to reload HAProxy!")
        return

    self._update_ready_status()
```

Note that we are also updating the root URL in the `service.conf` using the leader unit’s IP address if it is not provided through the config, similar to how this was done previously by reading the HAProxy relation when it joined.

Now, we can call this to update a unit’s HAProxy config:

```py
self._update_haproxy()
```

We need to call this in the following lifecycle hooks:

- When leadership changes or the replica relation changes, such as when a leader is elected or a unit is added or removed (`_leader_changed` is already called in all these cases, so we can just add it there)  
- The charm configuration changes, such as the worker count or enabling/disabling the gRPC services (`_on_config_changed`)

### **Ingress**

We still want to put the [Ingress Configurator charm](https://charmhub.io/ingress-configurator?channel=latest/edge) in front of our deployment to allow us to migrate to PS7, which [necessitates it](https://canonical-information-systems-documentation.readthedocs-hosted.com/en/latest/how-to/ps7-developer-onboarding/#machine-ingress). Installing HAProxy in the Landscape Server units themselves and routing traffic among the units grants us much greater control over the HAProxy configuration and allows us to handle things like mulit-port, multi-worker service processes and error files. It also greatly simplifies our integration with the Ingress Configurator charm, since we only need to use it to expose traffic on ports 80, 443, and the gRPC ports, and then integrate with a remote HAProxy offer. 

We will add the following `requires` endpoints to the Landscape Server charm:

```json
http-ingress:
  interface: ingress
  limit: 1
https-ingress:
  interface: ingress
  limit: 1
hostagent-messenger-ingress:
  interface: ingress
  limit: 1
ubuntu-installer-attach-ingress:
  interface: ingress
  limit: 1
```

Then, we can use the `IngressPerAppRequirer` charm library to pass our charm’s information to the relation data, for example:

```py
self.http_ingress = IngressPerAppRequirer(
    self,
    port=haproxy.FrontendPort.HTTP,
    relation_name="http-ingress",
    redirect_https=True,
)

self.https_ingress = IngressPerAppRequirer(
    self,
    port=haproxy.FrontendPort.HTTPS,
    relation_name="https-ingress",
    redirect_https=True,
)

if self.charm_config.enable_hostagent_messenger:
    self.hostagent_messenger_ingress = IngressPerAppRequirer(
        self,
        relation_name="hostagent-messenger-ingress",
        port=haproxy.FrontendPort.HOSTAGENT_MESSENGER,
        redirect_https=True,
    )

if self.charm_config.enable_ubuntu_installer_attach:
    self.ubuntu_installer_attach_ingress = IngressPerAppRequirer(
        self,
        relation_name="ubuntu-installer-attach-ingress",
        port=haproxy.FrontendPort.UBUNTU_INSTALLER_ATTTACH,
        redirect_https=True,
    )
```

Note that we don’t need to observe the lifecycle events of the ingress relations as we are not actually using the event URL for anything.

The `IngressPerAppRequirer` will automatically push the unit addresses and specified parameters (port, etc.) to a remote HAProxy charm when they integrate over the `haproxy-route` interface, so instantiating the class should be enough since it will already react to relation lifecycle changes, and the parameters we’re hardcoding should remain static. However, if needed, we can call the `provide_ingress_requirements` helper on the class to manually update the data.

#### gRPC 

For the gRPC services that need to listen on specific ports, we can use the [`grpc-frontend-port` config option on the Ingress Configurator charm](https://github.com/canonical/haproxy-operator/pull/287). All bundles or Terraform plans that deploy Landscape with the Ingress will need to set this option, and our docs should be updated accordingly. 

### **Example Bundle**

```json
description: Landscape Scalable Dev with internal HAProxy
applications:
  postgresql:
    channel: 16/stable
    charm: ch:postgresql
    num_units: 1
    to:
      - "3"
    options:
      plugin_plpython3u_enable: true
      plugin_ltree_enable: true
      plugin_intarray_enable: true
      plugin_debversion_enable: true
      plugin_pg_trgm_enable: true
      experimental_max_connections: 500
    base: ubuntu@24.04
  rabbitmq-server:
    channel: latest/edge
    charm: ch:rabbitmq-server
    num_units: 1
    to:
      - "4"
    options:
      consumer-timeout: 259200000
  landscape-server:
    charm: ../landscape-server_ubuntu@24.04-amd64.charm
    num_units: 3
    to:
      - "0"
      - "1"
      - "2"
    options:
      landscape_ppa: ppa:landscape/self-hosted-beta
      min_install: True
      enable_hostagent_messenger: True
      enable_ubuntu_installer_attach: True
      root_url: https://landscape.local/
    base: ubuntu@24.04
  hostagent-messenger-ingress:
    charm: ingress-configurator
    channel: latest/edge
    revision: 36
    num_units: 1
    to:
      - "0"
    constraints: arch=amd64
    options:
      paths: /
      hostname: landscape.local
  http-ingress:
    charm: ingress-configurator
    channel: latest/edge
    revision: 36
    num_units: 1
    to:
      - "0"
    constraints: arch=amd64
    options:
      paths: /
      hostname: landscape.local
  https-ingress:
    charm: ingress-configurator
    channel: latest/edge
    revision: 36
    num_units: 1
    to:
      - "0"
    constraints: arch=amd64
    options:
      paths: /
      hostname: landscape.local
  ubuntu-installer-attach-ingress:
    charm: ingress-configurator
    channel: latest/edge
    revision: 36
    num_units: 1
    to:
      - "0"
    constraints: arch=amd64
    options:
      paths: /
      hostname: landscape.local
  lb-certs:
    charm: self-signed-certificates
    channel: stable
    num_units: 1
    to:
      - "0"
    constraints: arch=amd64

machines:
  "0":
    constraints: arch=amd64
  "1":
    constraints: arch=amd64
  "2":
    constraints: arch=amd64
  "3":
    constraints: arch=amd64
  "4":
    constraints: arch=amd64

relations:
  - [landscape-server:inbound-amqp, rabbitmq-server]
  - [landscape-server:outbound-amqp, rabbitmq-server]
  - [landscape-server:database, postgresql:database]
  - [landscape-server:http-ingress, http-ingress:ingress]
  - [landscape-server:https-ingress, https-ingress:ingress]
  - [
      landscape-server:hostagent-messenger-ingress,
      hostagent-messenger-ingress:ingress,
    ]
  - [
      landscape-server:ubuntu-installer-attach-ingress,
      ubuntu-installer-attach-ingress:ingress,
    ]
  - [landscape-server:load-balancer-certificates, lb-certs:certificates]
```

### **Example generated HAProxy config**

```json
global
    maxconn 4096
    user haproxy
    group haproxy

    log /dev/log local0

    # generated 2026-01-07, Mozilla Guideline v5.7, HAProxy 2.8, OpenSSL 1.1.1w (UNSUPPORTED; end-of-life), intermediate config, no HSTS
    # https://ssl-config.mozilla.org/#server=haproxy&version=2.8&config=intermediate&openssl=1.1.1w&hsts=false&guideline=5.7
    # intermediate configuration
    ssl-default-bind-curves X25519:prime256v1:secp384r1
    ssl-default-bind-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305
    ssl-default-bind-ciphersuites TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256
    ssl-default-bind-options prefer-client-ciphers ssl-min-ver TLSv1.2 no-tls-tickets

    ssl-default-server-ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:DHE-RSA-CHACHA20-POLY1305
    ssl-default-server-ciphersuites TLS_AES_128_GCM_SHA256:TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256
    ssl-default-server-options ssl-min-ver TLSv1.2 no-tls-tickets

    tune.ssl.default-dh-param 2048

defaults
    log global
    mode http
    option httplog
    option dontlognull
    retries 3
    timeout queue 60000
    timeout connect 5000
    timeout client 120000
    timeout server 120000

    errorfile 403 /etc/haproxy/errors/unauthorized-haproxy.html
    errorfile 500 /etc/haproxy/errors/exception-haproxy.html
    errorfile 502 /etc/haproxy/errors/unplanned-offline-haproxy.html
    errorfile 503 /etc/haproxy/errors/unplanned-offline-haproxy.html
    errorfile 504 /etc/haproxy/errors/timeout-haproxy.html

frontend landscape-http
    bind [::]:80 v4v6
    mode http
    timeout client 300000
    timeout server 300000
    balance leastconn
    option httpchk HEAD / HTTP/1.0
    acl ping path_beg -i /ping
    acl repository path_beg -i /repository
    acl message path_beg -i /message-system
    acl attachment path_beg -i /attachment
    acl api path_beg -i /api
    acl hashids path_beg -i /hash-id-databases
    acl package-upload path_beg -i /upload
    http-request replace-path ^([^\ ]*)\ /upload/(.*) /\1
    use_backend landscape-http-message if message
    use_backend landscape-http-message if attachment
    use_backend landscape-http-api if api
    use_backend landscape-http-ping if ping
    use_backend landscape-http-hashid-databases if hashids
    use_backend landscape-http-package-upload if package-upload
    acl metrics path_end /metrics
    http-request deny if metrics
    acl prometheus_metrics path_beg -i /metrics
    http-request deny if prometheus_metrics

    redirect scheme https unless ping OR repository

    default_backend landscape-http-appserver

frontend landscape-https
    bind [::]:443 v4v6 ssl crt /etc/haproxy/haproxy.pem
    mode http
    timeout client 300000
    timeout server 300000
    balance leastconn
    option httpchk HEAD / HTTP/1.0
    http-request set-header X-Forwarded-Proto https
    acl ping path_beg -i /ping
    acl repository path_beg -i /repository
    acl message path_beg -i /message-system
    acl attachment path_beg -i /attachment
    acl api path_beg -i /api
    acl hashids path_beg -i /hash-id-databases
    acl package-upload path_beg -i /upload
    http-request replace-path ^([^\ ]*)\ /upload/(.*) /\1
    use_backend landscape-https-message if message
    use_backend landscape-https-message if attachment
    use_backend landscape-https-api if api
    use_backend landscape-https-ping if ping
    use_backend landscape-https-hashid-databases if hashids
    use_backend landscape-https-package-upload if package-upload
    acl metrics path_end /metrics
    http-request deny if metrics
    acl prometheus_metrics path_beg -i /metrics
    http-request deny if prometheus_metrics

    default_backend landscape-https-appserver

frontend landscape-hostagent-messenger
    bind [::]:6554 v4v6 ssl crt /etc/haproxy/haproxy.pem alpn h2,http/1.1
    mode http

    default_backend landscape-hostagent-messenger

frontend landscape-ubuntu-installer-attach
    bind [::]:50051 v4v6 ssl crt /etc/haproxy/haproxy.pem alpn h2,http/1.1
    mode http
    acl host_found hdr(host) -m found
    http-request set-var(req.full_fqdn) hdr(authority) if !host_found
    http-request set-var(req.full_fqdn) hdr(host) if host_found
    http-request set-header X-FQDN %[var(req.full_fqdn)]

    default_backend landscape-ubuntu-installer-attach

backend landscape-http-appserver
    mode http
    timeout server 300000
    server landscape-appserver-10-1-77-18-0 10.1.77.18:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-18-1 10.1.77.18:8081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-229-0 10.1.77.229:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-229-1 10.1.77.229:8081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-42-0 10.1.77.42:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-42-1 10.1.77.42:8081 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-http-ping
    mode http
    timeout server 300000
    server landscape-pingserver-10-1-77-18-0 10.1.77.18:8070 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-18-1 10.1.77.18:8071 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-229-0 10.1.77.229:8070 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-229-1 10.1.77.229:8071 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-42-0 10.1.77.42:8070 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-42-1 10.1.77.42:8071 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-http-message
    mode http
    timeout server 300000
    server landscape-message-server-10-1-77-18-0 10.1.77.18:8090 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-18-1 10.1.77.18:8091 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-229-0 10.1.77.229:8090 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-229-1 10.1.77.229:8091 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-42-0 10.1.77.42:8090 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-42-1 10.1.77.42:8091 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-http-api
    mode http
    timeout server 300000
    server landscape-api-10-1-77-18-0 10.1.77.18:9080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-18-1 10.1.77.18:9081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-229-0 10.1.77.229:9080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-229-1 10.1.77.229:9081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-42-0 10.1.77.42:9080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-42-1 10.1.77.42:9081 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-http-package-upload
    mode http
    timeout server 300000
    server landscape-leader-package-upload 10.1.77.18:9100 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-http-hashid-databases
    mode http
    timeout server 300000
    server landscape-leader-appserver-0 10.1.77.18:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-leader-appserver-1 10.1.77.18:8081 check inter 5000 rise 2 fall 5 maxconn 50


backend landscape-https-appserver
    mode http
    timeout server 300000
    server landscape-appserver-10-1-77-18-0 10.1.77.18:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-18-1 10.1.77.18:8081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-229-0 10.1.77.229:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-229-1 10.1.77.229:8081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-42-0 10.1.77.42:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-appserver-10-1-77-42-1 10.1.77.42:8081 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-https-ping
    mode http
    timeout server 300000
    server landscape-pingserver-10-1-77-18-0 10.1.77.18:8070 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-18-1 10.1.77.18:8071 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-229-0 10.1.77.229:8070 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-229-1 10.1.77.229:8071 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-42-0 10.1.77.42:8070 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-pingserver-10-1-77-42-1 10.1.77.42:8071 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-https-message
    mode http
    timeout server 300000
    server landscape-message-server-10-1-77-18-0 10.1.77.18:8090 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-18-1 10.1.77.18:8091 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-229-0 10.1.77.229:8090 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-229-1 10.1.77.229:8091 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-42-0 10.1.77.42:8090 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-message-server-10-1-77-42-1 10.1.77.42:8091 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-https-api
    mode http
    timeout server 300000
    server landscape-api-10-1-77-18-0 10.1.77.18:9080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-18-1 10.1.77.18:9081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-229-0 10.1.77.229:9080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-229-1 10.1.77.229:9081 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-42-0 10.1.77.42:9080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-api-10-1-77-42-1 10.1.77.42:9081 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-https-package-upload
    mode http
    timeout server 300000
    server landscape-leader-package-upload 10.1.77.18:9100 check inter 5000 rise 2 fall 5 maxconn 50

backend landscape-https-hashid-databases
    mode http
    timeout server 300000
    server landscape-leader-appserver-0 10.1.77.18:8080 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-leader-appserver-1 10.1.77.18:8081 check inter 5000 rise 2 fall 5 maxconn 50


backend landscape-hostagent-messenger
    mode http
    timeout server 300000
    server landscape-hostagent-messenger-10-1-77-18 10.1.77.18:50052 proto h2 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-hostagent-messenger-10-1-77-229 10.1.77.229:50052 proto h2 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-hostagent-messenger-10-1-77-42 10.1.77.42:50052 proto h2 check inter 5000 rise 2 fall 5 maxconn 50


backend landscape-ubuntu-installer-attach
    mode http
    timeout server 300000
    server landscape-ubuntu-installer-attach-10-1-77-18 10.1.77.18:53354 proto h2 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-ubuntu-installer-attach-10-1-77-229 10.1.77.229:53354 proto h2 check inter 5000 rise 2 fall 5 maxconn 50
    server landscape-ubuntu-installer-attach-10-1-77-42 10.1.77.42:53354 proto h2 check inter 5000 rise 2 fall 5 maxconn 50
```

