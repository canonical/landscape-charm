import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv

from lib.hook import Hook
from lib.apt import Apt


class UpgradeCharmHook(Hook):
    """Execute upgrade-charm hook logic."""

    def __init__(self, hookenv=hookenv, fetch=fetch, subprocess=subprocess):
        super(UpgradeCharmHook, self).__init__(hookenv=hookenv)
        self._fetch = fetch
        self._subprocess = subprocess

    def _run(self):
        # Set APT sources and install Landscape packages
        apt = Apt(
            hookenv=self._hookenv, fetch=self._fetch,
            subprocess=self._subprocess)
        apt.set_sources()
        apt.install_packages()
