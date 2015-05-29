import subprocess

from charmhelpers.core import hookenv

from lib.hook import Hook
from lib.paths import LSCTL


class ResumeAction(Hook):
    """Resume all Landscape services on the unit."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        super(ResumeAction, self).__init__(hookenv=hookenv)
        self._subprocess = subprocess

    def _run(self):
        self._subprocess.check_call((LSCTL, "start"))
