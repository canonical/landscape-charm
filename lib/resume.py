import subprocess

from charmhelpers.core import hookenv

from lib.action import MaintenanceAction
from lib.error import CharmError
from lib.paths import default_paths, LSCTL

class ProcessesNotStartedError(CharmError):
    """Some of the Landscape server processes couldnt' be started."""


class ResumeAction(MaintenanceAction):
    """Resume all Landscape services on the unit."""

    def __init__(self, hookenv=hookenv, paths=default_paths,
                 subprocess=subprocess):
        super(ResumeAction, self).__init__(hookenv=hookenv, paths=paths)
        self._subprocess = subprocess

    def _run(self):
        self._subprocess.check_call((LSCTL, "start"))
        try:
            self._subprocess.check_call((LSCTL, "status"))
        except subprocess.CalledProcessError:
            raise ProcessesNotStartedError()
