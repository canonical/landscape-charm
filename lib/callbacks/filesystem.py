# Filesystem-related callbacks

import os
import base64
import urllib2

from charmhelpers.core import host
from charmhelpers.core.services.base import ManagerCallback

from lib.error import CharmError
from lib.paths import default_paths
from lib.utils import get_required_data


class LicenseFileUnreadableError(CharmError):
    """Unable to read the license file."""

    def __init__(self, license_file_value):
        message = "Could not read license file from '%s'" % license_file_value
        super(LicenseFileUnreadableError, self).__init__(message)


class LicenseDataBase64DecodeError(CharmError):
    """Problem base64-decoding license data."""

    def __init__(self):
        message = "Error base64-decoding license-file data."
        super(LicenseDataBase64DecodeError, self).__init__(message)


class EnsureConfigDir(ManagerCallback):
    """Ensure that the config dir for the configured deployment mode exists.

    XXX This is a temporary workaround till we make the Landscape server
        code always look at the same location for configuration files.
    """
    def __init__(self, paths=default_paths):
        self._paths = paths

    def __call__(self, manager, service_name, event_name):
        # Lookup the deployment mode
        hosted = get_required_data(manager, service_name, "hosted")
        deployment_mode = hosted[0]["deployment-mode"]

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


class WriteLicenseFile(ManagerCallback):
    """Write a license file if it is specified in the config file."""

    def __init__(self, host=host, paths=default_paths):
        self._host = host
        self._paths = paths

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
            try:
                license_file = urllib2.urlopen(license_file_value)
                license_data = license_file.read()
            except urllib2.URLError:
                raise LicenseFileUnreadableError(license_file_value)
        else:
            try:
                license_data = base64.b64decode(license_file_value)
            except TypeError:
                raise LicenseDataBase64DecodeError()

        self._host.write_file(
            self._paths.license_file(), license_data,
            owner="landscape", group="root", perms=0o640)
