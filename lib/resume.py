import subprocess

from charmhelpers.core import hookenv

from lib.action import MaintenanceAction
from lib.error import CharmError
from lib.paths import default_paths, LSCTL


class ProcessesNotStartedError(CharmError):
    """Some of the Landscape server processes couldnt' be started."""

    def __init__(self, start_output, status_output):
        message = "Some services failed to start.\n\n{}\n\n{}".format(
            start_output, status_output)
        super(ProcessesNotStartedError, self).__init__(message)


class ResumeAction(MaintenanceAction):
    """Resume all Landscape services on the unit."""

    def __init__(self, hookenv=hookenv, paths=default_paths,
                 subprocess=subprocess):
        super(ResumeAction, self).__init__(hookenv=hookenv, paths=paths)
        self._subprocess = subprocess

    def _run(self):
        start_output = self._subprocess.check_output((LSCTL, "start"))
        try:
            self._subprocess.check_output((LSCTL, "status"))
        except subprocess.CalledProcessError as status_error:
            self._subprocess.call((LSCTL, "stop"))
            raise ProcessesNotStartedError(start_output, status_error.output)
