import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv

from lib.hook import Hook
from lib.apt import Apt


class ConfigHook(Hook):
    """Execute config-changed hook logic."""

    def __init__(self, hookenv=hookenv, fetch=fetch, subprocess=subprocess):
        super(ConfigHook, self).__init__(hookenv=hookenv)
        self._fetch = fetch
        self._subprocess = subprocess

    def _run(self):
        # Re-set APT sources, if the have changed.
        apt = Apt(
            hookenv=self._hookenv, fetch=self._fetch,
            subprocess=self._subprocess)
        apt.set_sources()

        config = self._hookenv.config()
        config.save()
