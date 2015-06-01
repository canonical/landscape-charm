from charmhelpers.core import hookenv
from charmhelpers import fetch

from lib.apt import PACKAGES
from lib.hook import MaintenanceHook
from lib.paths import default_paths


class UpgradeAction(MaintenanceHook):
    """Execute package upgrade action logic."""

    def __init__(self, hookenv=hookenv, fetch=fetch, paths=default_paths):
        super(UpgradeAction, self).__init__(hookenv=hookenv, paths=paths)
        self._fetch = fetch

    def _run(self):
        self._fetch.apt_update(fatal=True)
        apt_install_options = [
            # Ensure we keep the existing service.conf and
            # /etc/defaults/landscape-server configuration files
            # (force-confold) and only install config files which
            # have not been changed (force-confdef).
            "--option=Dpkg::Options::=--force-confdef",
            "--option=Dpkg::Options::=--force-confold",
        ]
        self._fetch.apt_install(PACKAGES, apt_install_options, fatal=True)
