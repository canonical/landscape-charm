# Filesystem-related callbacks

import os
import base64
import urllib2

import charmhelpers.core.host as host
from charmhelpers.core.services.base import ManagerCallback

CONFIGS_DIR = "/opt/canonical/landscape/configs"
SSL_CERTS_DIR = "/etc/ssl/certs"


class EnsureConfigDir(ManagerCallback):
    """Ensure that the config dir for the configured deployment mode exists.

    XXX This is a temporary workaround till we make the Landscape server
        code always look at the same location for configuration files.
    """
    def __init__(self, configs_dir=CONFIGS_DIR):
        self._configs_dir = configs_dir

    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)

        # Lookup the deployment mode
        for data in service.get("required_data"):
            if "hosted" in data:
                deployment_mode = data["hosted"][0]["deployment-mode"]
                break

        # Create a symlink for the config directory
        config_link = os.path.join(self._configs_dir, deployment_mode)
        if not os.path.exists(config_link):
            standalone_dir = os.path.join(self._configs_dir, "standalone")
            os.symlink(standalone_dir, config_link)


class WriteCustomSSLCertificate(ManagerCallback):
    """Write the custom SSL certificate used, if any.

    This callback will write any custom SSL certificate that has been set,
    either explicitly with the 'ssl-cert' config key, or implicitly (by
    using haproxy's self-signed one).
    """
    def __init__(self, ssl_certs_dir=SSL_CERTS_DIR):
        self._ssl_certs_dir = ssl_certs_dir

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
        ssl_cert_path = os.path.join(
            self._ssl_certs_dir, "landscape_server_ca.crt")
        with open(ssl_cert_path, "w") as fd:
            fd.write(base64.b64decode(ssl_cert))


class WriteLicenseFile(ManagerCallback):
    """Write a license file if it is specified in the config file."""

    def __init__(self, license_file="/etc/landscape/license.txt", host=host):
        self._host = host
        self._license_file = license_file

    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)

        license_file_value = None

        # Lookup the deployment mode
        for data in service.get("required_data"):
            if "config" in data:
                license_file_value = data["config"].get("license-file")
                break

        if license_file_value is None:
            return

        if (license_file_value.startswith("file://") or
                license_file_value.startswith("http://") or
                license_file_value.startswith("https://")):
            license_file = urllib2.urlopen(license_file_value)
            license_data = license_file.read()
        else:
            license_data = base64.b64decode(license_file_value)

        self._host.write_file(
            self._license_file, license_data,
            owner="landscape", group="root", perms=0o640)
