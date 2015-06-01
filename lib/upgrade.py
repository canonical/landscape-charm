import subprocess

from charmhelpers.core import hookenv
from charmhelpers import fetch

from lib.apt import Apt
from lib.hook import Hook


class UpgradeAction(Hook):
    """Execute package upgrade action logic."""

    def __init__(self, hookenv=hookenv, fetch=fetch, subprocess=subprocess):
        super(UpgradeAction, self).__init__(hookenv=hookenv)
        self._fetch = fetch
        self._subprocess = subprocess

    def _run(self):
        apt_install_options = [
            # Ensure we keep the existing service.conf and
            # /etc/defaults/landscape-server configuration files
            # (force-confold) and only install config files which
            # have not been changed (force-confdef).
            "--option=Dpkg::Options::=--force-confdef",
            "--option=Dpkg::Options::=--force-confold",
        ]
        apt = Apt(
            hookenv=self._hookenv, fetch=self._fetch,
            subprocess=self._subprocess)
        apt.set_sources(force_update=True)
        apt.install_packages(apt_install_options)
