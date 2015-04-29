# Filesystem-related callbacks

import os
import base64

from charmhelpers.core.services.base import ManagerCallback

from lib.paths import default_paths

SSL_CERTS_DIR = "/etc/ssl/certs"


class EnsureConfigDir(ManagerCallback):
    """Ensure that the config dir for the configured deployment mode exists.

    XXX This is a temporary workaround till we make the Landscape server
        code always look at the same location for configuration files.
    """
    def __init__(self, paths=default_paths):
        self._paths = paths

    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)

        # Lookup the deployment mode
        for data in service.get("required_data"):
            if "hosted" in data:
                deployment_mode = data["hosted"][0]["deployment-mode"]
                break

        # Create a symlink for the config directory
        config_link = self._paths.config_link(deployment_mode)
        if not os.path.exists(config_link):
            os.symlink(self._paths.config_dir(), config_link)


class WriteCustomSSLCertificate(ManagerCallback):
    """Write the custom SSL certificate used, if any.

    This callback will write any custom SSL certificate that has been set,
    either explicitly with the 'ssl-cert' config key, or implicitly (by
    using haproxy's self-signed one).
    """
    def __init__(self, paths=default_paths):
        self._paths = paths

    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)

        # Lookup the SSL certificates
        for data in service.get("required_data"):
            if "website" in data:
                # We arbitrarily grab the SSL certificate from the first
                # haproxy unit we're related to. All other units will expose
                # the same certificate.
                haproxy_ssl_cert = data["website"][0]["ssl_cert"]
            if "config" in data:
                config_ssl_cert = data["config"].get("ssl-cert")

        # Use the configured SSL cert if available, otherwise the haproxy one
        ssl_cert = config_ssl_cert or haproxy_ssl_cert

        # Write out the data
        with open(self._paths.ssl_certificate(), "w") as fd:
            fd.write(base64.b64decode(ssl_cert))
