import subprocess

from charmhelpers.core import hookenv

from lib.apt import PACKAGES
from lib.hook import Hook

class UpgradeAction(Hook):
    """Execute pause action logic."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        super(UpgradeAction, self).__init__(hookenv=hookenv)
        self._subprocess = subprocess

    def _run(self):
        self._subprocess.check_call(("apt-get", "update", "-y"))
        apt_install_call = [
            "apt-get", "install", "-y",
            # Ensure we keep the existing service.conf and
            # /etc/defaults/landscape-server configuration files
            #(force-confold) and only install config files which
            # have not been changed (force-confdef).
            "-o", 'Dpkg::Options::="--force-confdef"',
            "-o", 'Dpkg::Options::="--force-confold"',
        ]
        apt_install_call.extend(PACKAGES)
        self._subprocess.check_call(apt_install_call)
