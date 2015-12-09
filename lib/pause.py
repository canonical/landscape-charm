import subprocess

from charmhelpers.core import hookenv

from lib.action import Action
from lib.paths import LSCTL


class PauseAction(Action):
    """Execute pause action logic."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        super(PauseAction, self).__init__(hookenv=hookenv)
        self._subprocess = subprocess

    def _run(self):
        self._hookenv.status_set("maintenance", "Stopping services.")
        self._subprocess.check_call((LSCTL, "stop"))
        self._hookenv.status_set("maintenance", "Services stopped.")
