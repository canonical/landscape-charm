import base64
import os
import yaml

from lib.hook import HookError

from charmhelpers.core import hookenv
from charmhelpers.core.services.helpers import RelationContext

SERVICE_PORTS = {
    "http": 80,
    "https": 443,
}
SERVICE_OPTIONS = {
    "http": [
        "mode http",
        "balance leastconn",
        "option httpchk HEAD / HTTP/1.0",
        "acl ping path_beg -i /ping",
        "redirect scheme https unless ping",
        "use_backend landscape-ping if ping",
    ],
    "https": [
        "mode http",
        "balance leastconn",
        "option httpchk HEAD / HTTP/1.0",
        "http-request set-header X-Forwarded-Proto https",
        "acl message path_beg -i /message-system",
        "acl api path_beg -i /api",
        "use_backend landscape-message if message",
        "use_backend landscape-api if api",
    ],
}
SERVER_PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
}
SERVER_OPTIONS = [
    "check",
    "inter 5000",
    "rise 2",
    "fall 5",
    "maxconn 50",
]
ERRORFILES_MAP = {
    # Add 503 only for now since that's what the integration tests
    # check.
    "503": "unplanned-offline-haproxy.html",
    # TODO: Due to bug #1437366 the command line call to "relation-set"
    # will fail by reaching MAX_ARGS if too many errorfiles are set.
    # Until fixed let's set only one errorfile to assert it works.
    #"403": "unauthorized-haproxy.html",
    #"500": "exception-haproxy.html",
    #"502": "unplanned-offline-haproxy.html",
    #"504": "timeout-haproxy.html",
}
OFFLINE_FOLDER = "/opt/canonical/landscape/canonical/landscape/offline"


class HAProxyProvider(RelationContext):
    """Relation data provider feeding haproxy service configuration."""

    name = "website"
    interface = "http"
    required_keys = ["services"]

    def __init__(self, hookenv=hookenv, offline_dir=OFFLINE_FOLDER):
        self._hookenv = hookenv
        self._offline_dir = offline_dir
        super(HAProxyProvider, self).__init__()

    def provide_data(self):
        return {"services": yaml.safe_dump([self._http(), self._https()])}

    def _http(self):
        """Return the service configuration for the HTTP frontend."""
        service = self._service("http")
        service.update({
            "servers": [self._server("appserver")],
            "backends": [
                self._backend("ping", [self._server("pingserver")]),
            ]
        })
        return service

    def _https(self):
        """Return the service configuration for the HTTPS frontend."""
        service = self._service("https")
        service.update({
            "crts": ["DEFAULT"],
            "servers": [self._server("appserver")],
            "backends": [
                self._backend("message", [self._server("message-server")]),
                self._backend("api", [self._server("api")]),
            ],
        })
        return service

    def _service(self, name):
        """Return a basic service configuration, with no servers or backends.

        Servers and backends are supposed to be filled by calling code.

        @param name: The base name of the frontend service.
        """
        return {
            "service_name": "landscape-%s" % name,
            "service_host": "0.0.0.0",
            "service_port": SERVICE_PORTS[name],
            "service_options": SERVICE_OPTIONS[name],
            "errorfiles": self._get_error_files()
        }

    def _backend(self, name, servers):
        """Return a backend for the service with the given name and servers.

        @param name: Which backend service to use. Possible values are 'api',
            'message' or 'ping'.
        @param servers: List of servers belonging to this backend.
        """
        return {
            "backend_name": "landscape-%s" % name,
            "servers": servers,
        }

    def _server(self, name):
        """Return a server 4-tuple, as expected by the HAProxy charm.

        @param name: The base name of the server, it will be expanded with
            the local unit name to make each server have a unique name.
        """
        server_ip = self._hookenv.unit_private_ip()
        unit_name = self._hookenv.local_unit()
        server_name = "landscape-%s-%s" % (name, unit_name.replace("/", "-"))
        server_port = SERVER_PORTS[name]
        return (server_name, server_ip, server_port, SERVER_OPTIONS)

    def _get_error_files(self):
        """Return the errorfiles configuration."""
        result = []

        for error_code, file_name in sorted(ERRORFILES_MAP.items()):
            content = None
            path = os.path.join(self._offline_dir, file_name)

            try:
                with open(path, "r") as error_file:
                    content = error_file.read()
            except IOError as error:
                raise HookError(
                    "Could not read '%s' (%s)!" % (path, str(error)))

            entry = {"http_status": error_code,
                     "content": base64.b64encode(content)}
            result.append(entry)

        return result
