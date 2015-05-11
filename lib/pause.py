import subprocess

from charmhelpers.core import hookenv

from lib.hook import Hook
from lib.paths import LSCTL


class PauseAction(Hook):
    """Execute pause action logic."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        super(PauseAction, self).__init__(hookenv=hookenv)
        self._subprocess = subprocess

    def _run(self):
        self._subprocess.check_call((LSCTL, "stop"))
        self._subprocess.check_call(("service", "cron", "stop"))
