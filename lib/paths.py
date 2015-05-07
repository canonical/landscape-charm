import os

# Plain paths
SERVICE_CONF = "/etc/landscape/service.conf"
DEFAULT_FILE = "/etc/default/landscape-server"
SSL_CERT_PATH = "/etc/ssl/certs/landscape_server_ca.crt"
CONFIG_DIR = "/opt/canonical/landscape/configs/standalone"
OFFLINE_DIR = "/opt/canonical/landscape/canonical/landscape/offline"
LICENSE_FILE = "/etc/landscape/license.txt"
LSCTL = "/usr/bin/lsctl"


class Paths(object):
    """Encapsulate all filesystem paths that the charm needs to know about.

    This is a convenience useful for testing (as tests can pass a different
    root_dir) and also to keep the list integration points with the file
    system all in one place.
    """

    def __init__(self, root_dir="/"):
        self._root_dir = root_dir

    def service_conf(self):
        """Return the path to the Landscape service.conf file."""
        return self._get_path(SERVICE_CONF)

    def default_file(self):
        """Return the path to the Landscape etc/default file."""
        return self._get_path(DEFAULT_FILE)

    def config_dir(self):
        """Return the path to the standalone config directory."""
        return self._get_path(CONFIG_DIR)

    def config_link(self, deployment_mode):
        """Return the path to config link in the configs directory.

        XXX Eventually we're going to consolidate the various directories
            under /opt/canonical/landscape/configs/, but for now this is
            needed because the server code expects that. See also the
            EnsureConfigDir callback.
        """
        return self._get_path(os.path.dirname(CONFIG_DIR), deployment_mode)

    def offline_dir(self):
        """Return the path to the Landscape offline pages directory."""
        return self._get_path(OFFLINE_DIR)

    def ssl_certificate(self):
        """Return the path to the SSL certificate used by Landscape."""
        return self._get_path(SSL_CERT_PATH)

    def license_file(self):
        """Return the path to the Landscape license file."""
        return self._get_path(LICENSE_FILE)

    def _get_path(self, *paths):
        """Return the actual path of the given plain path."""
        path = os.path.join(*paths)
        if self._root_dir != "/":
            path = os.path.join(self._root_dir, path[1:])
        return path


default_paths = Paths()
