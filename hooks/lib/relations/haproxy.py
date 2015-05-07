import base64
import os
import yaml

from charmhelpers.core import hookenv
from charmhelpers.core.services.helpers import RelationContext

from lib.hook import HookError
from lib.paths import default_paths


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
        "acl package-upload path_beg -i /package-upload",
        "use_backend landscape-message if message",
        "use_backend landscape-api if api",
        "use_backend package-upload if package-upload",
    ],
}
SERVER_PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
    "package-upload": 9090,
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
    # "403": "unauthorized-haproxy.html",
    # "500": "exception-haproxy.html",
    # "502": "unplanned-offline-haproxy.html",
    # "504": "timeout-haproxy.html",
}


class HAProxyProvider(RelationContext):
    """Relation data provider feeding haproxy service configuration."""

    name = "website"
    interface = "http"
    required_keys = ["services"]

    def __init__(self, hookenv=hookenv, paths=default_paths, is_leader=False):
        self._hookenv = hookenv
        self._paths = paths
        self._is_leader = is_leader
        super(HAProxyProvider, self).__init__()

    def provide_data(self):
        return {
            "services": yaml.safe_dump([self._get_http(), self._get_https()])
        }

    def _get_http(self):
        """Return the service configuration for the HTTP frontend."""
        service = self._get_service("http")
        service.update({
            "servers": [self._get_server("appserver")],
            "backends": [
                self._get_backend("ping", [self._get_server("pingserver")]),
            ]
        })
        return service

    def _get_https(self):
        """Return the service configuration for the HTTPS frontend."""
        service = self._get_service("https")
        service.update({
            "crts": self._get_ssl_certificate(),
            "servers": [self._get_server("appserver")],
            "backends": [
                self._get_backend(
                    "message", [self._get_server("message-server")]),
                self._get_backend("api", [self._get_server("api")]),
            ],
        })
        if self._is_leader:
            service["backends"].append(
                self._get_backend(
                    "package-upload", [self._get_server("package-upload")]))
        return service

    def _get_service(self, name):
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

    def _get_backend(self, name, servers):
        """Return a backend for the service with the given name and servers.

        @param name: Which backend service to use. Possible values are 'api',
            'message' or 'ping'.
        @param servers: List of servers belonging to this backend.
        """
        return {
            "backend_name": "landscape-%s" % name,
            "servers": servers,
        }

    def _get_server(self, name):
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
            path = os.path.join(self._paths.offline_dir(), file_name)

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

    def _get_ssl_certificate(self):
        """Get the PEM certificate to send to HAproxy through the relation.

        In case no certificate is defined, we send the "DEFAULT" keyword
        instead.
        """
        config = self._hookenv.config()
        ssl_cert = config.get("ssl-cert", "")
        ssl_key = config.get("ssl-key", "")

        if ssl_cert == "":
            # If no SSL certificate is specified, simply return "DEFAULT".
            self._hookenv.log(
                "No SSL configuration keys found, asking HAproxy to use the"
                " 'DEFAULT' certificate.")
            return ["DEFAULT"]

        if ssl_key == "":
            # A cert is specified, but no key. Error out.
            raise HookError(
                "'ssl-cert' is specified but 'ssl-key' is missing!")

        try:
            decoded_cert = base64.b64decode(ssl_cert)
            decoded_key = base64.b64decode(ssl_key)
        except TypeError:
            raise HookError(
                "The supplied 'ssl-cert' or 'ssl-key' parameter is not valid"
                " base64.")

        decoded_pem = "%s\n%s" % (decoded_cert, decoded_key)

        self._hookenv.log(
            "Asking HAproxy to use the supplied 'ssl-cert' and 'ssl-key'"
            " parameters.")

        # Return the base64 encoded pem.
        return [base64.b64encode(decoded_pem)]


class HAProxyRequirer(RelationContext):
    """Relation data provider feeding haproxy service configuration."""

    name = "website"
    interface = "http"
    required_keys = ["public-address", "ssl_cert"]
