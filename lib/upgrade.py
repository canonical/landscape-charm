import os.path

from charmhelpers.core import hookenv
from charmhelpers import fetch

from lib.apt import PACKAGES
from lib.hook import Hook, HookError
from lib.paths import default_paths


class UpgradeAction(Hook):
    """Execute package upgrade action logic."""

    def __init__(self, hookenv=hookenv, fetch=fetch, paths=default_paths):
        super(UpgradeAction, self).__init__(hookenv=hookenv)
        self._fetch = fetch
        self._paths = paths

    def _run(self):
        if not os.path.exists(self._paths.maintenance_flag()):
            raise HookError(
                "Upgrade action can only be called on a unit in paused state.")
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
