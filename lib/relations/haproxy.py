import base64
import os
import yaml

from charmhelpers.core import hookenv
from charmhelpers.core.services.helpers import RelationContext

from lib.error import CharmError
from lib.paths import default_paths


SERVICE_PORTS = {
    "http": 80,
    "https": 443,
}
SERVICE_OPTIONS = {
    "http": [
        "mode http",
        # WARNING: our AJAX long-polling needs the client/server timeouts
        # to be greater than txlongpoll.frontend.QueueManager.message_timeout,
        # which by default is 270 seconds. If you change the values of the
        # timeouts below, please change QueueManager.message_timeout too.
        "timeout client 300000",
        "timeout server 300000",
        "balance leastconn",
        "option httpchk HEAD / HTTP/1.0",
        "acl ping path_beg -i /ping",
        "redirect scheme https unless ping",
        "use_backend landscape-ping if ping",
    ],
    "https": [
        "mode http",
        "timeout client 300000",
        "timeout server 300000",
        "balance leastconn",
        "option httpchk HEAD / HTTP/1.0",
        "http-request set-header X-Forwarded-Proto https",
        "acl message path_beg -i /message-system",
        "acl attachment path_beg -i /attachment",
        "acl api path_beg -i /api",
        "use_backend landscape-message if message",
        "use_backend landscape-message if attachment",
        "use_backend landscape-api if api",
    ],
}
SERVER_BASE_PORTS = {
    "appserver": 8080,
    "pingserver": 8070,
    "message-server": 8090,
    "api": 9080,
    "package-upload": 9100,
}
SERVER_OPTIONS = [
    "check",
    "inter 5000",
    "rise 2",
    "fall 5",
    "maxconn 50",
]
ERRORFILES_MAP = {
    "403": "unauthorized-haproxy.html",
    "500": "exception-haproxy.html",
    "502": "unplanned-offline-haproxy.html",
    "503": "unplanned-offline-haproxy.html",
    "504": "timeout-haproxy.html",
}


class SSLCertificateKeyMissingError(CharmError):
    """SSL certificate is specificed but ssl-key configuration is missing."""

    def __init__(self):
        message = "'ssl-cert' is specified but 'ssl-key' is missing!"
        super(SSLCertificateKeyMissingError, self).__init__(message)


class SSLCertificateInvalidDataError(CharmError):
    """SSL certificate configuration is invalid."""

    def __init__(self):
        message = (
            "The supplied 'ssl-cert' or 'ssl-key' parameters are "
            "not valid base64.")
        super(SSLCertificateInvalidDataError, self).__init__(message)


class ErrorFilesConfigurationError(CharmError):
    """HAProxy error-files configuration problem."""

    def __init__(self, path, message):
        message = "Could not read '%s' (%s)!" % (path, message)
        super(ErrorFilesConfigurationError, self).__init__(message)


class HAProxyProvider(RelationContext):
    """Relation data provider feeding haproxy service configuration."""

    name = "website"
    interface = "http"
    required_keys = ["services"]

    def __init__(self, per_service_counts, hookenv=hookenv,
                 paths=default_paths):
        self._hookenv = hookenv
        self._per_service_counts = per_service_counts
        self._paths = paths
        super(HAProxyProvider, self).__init__()

    def provide_data(self):
        return {
            "services": yaml.safe_dump([self._get_http(), self._get_https()])
        }

    def _get_http(self):
        """Return the service configuration for the HTTP frontend."""
        service = self._get_service("http")
        service.update({
            "servers": self._get_servers("appserver"),
            "backends": [
                self._get_backend("ping", self._get_servers("pingserver")),
            ]
        })
        return service

    def _get_https(self):
        """Return the service configuration for the HTTPS frontend."""

        service = self._get_service("https")
        backends = [
            self._get_backend("message", self._get_servers("message-server")),
            self._get_backend("api", self._get_servers("api")),
        ]
        if self._hookenv.is_leader():
            self._hookenv.log(
                "This unit is the juju leader: Writing package-upload backends"
                " entry.")
            service["service_options"].extend([
                "acl package-upload path_beg -i /upload",
                "use_backend landscape-package-upload if package-upload",
                "reqrep ^([^\\ ]*)\\ /upload/(.*) \\1\ /\\2",
            ])
            backends.append(
                self._get_backend(
                    "package-upload", self._get_servers("package-upload")))
        else:
            self._hookenv.log(
                "This unit is not the juju leader: not writing package-upload"
                " backends entry.")

        service.update({
            "crts": self._get_ssl_certificate(),
            "servers": self._get_servers("appserver"),
            "backends": backends,
        })

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
            # Copy the service options, since it will be modified if
            # we're the leader.
            "service_options": SERVICE_OPTIONS[name][:],
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

    def _get_servers(self, name):
        """Return a list of server 4-tuples, as expected by the HAProxy charm.

        When a service runs more than one process, process index will be
        appended to the server name.

        @param name: The base name of the server, it will be expanded with
            the local unit name to make each server have a unique name.

        """
        server_ip = self._hookenv.unit_private_ip()
        unit_name = self._hookenv.local_unit()
        server_name = "landscape-%s-%s" % (name, unit_name.replace("/", "-"))
        server_base_port = SERVER_BASE_PORTS[name]
        requested_processes = self._per_service_counts.get(name, 1)

        # When only one process for a service is started, return it.
        if requested_processes == 1:
            return [(server_name, server_ip, server_base_port, SERVER_OPTIONS)]

        servers = []
        for process_count in range(requested_processes):
            servers.append(
                (server_name + '-%d' % process_count, server_ip,
                 server_base_port + process_count, SERVER_OPTIONS))
        return servers

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
                raise ErrorFilesConfigurationError(path, str(error))

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
            raise SSLCertificateKeyMissingError()

        try:
            decoded_cert = base64.b64decode(ssl_cert)
            decoded_key = base64.b64decode(ssl_key)
        except TypeError:
            raise SSLCertificateInvalidDataError()

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
