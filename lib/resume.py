import subprocess

from charmhelpers.core import hookenv

from lib.hook import MaintenanceHook
from lib.paths import default_paths, LSCTL


class ResumeAction(MaintenanceHook):
    """Resume all Landscape services on the unit."""

    def __init__(self, hookenv=hookenv, paths=default_paths,
                 subprocess=subprocess):
        super(ResumeAction, self).__init__(hookenv=hookenv, paths=paths)
        self._subprocess = subprocess

    def _run(self):
        self._subprocess.check_call((LSCTL, "start"))
