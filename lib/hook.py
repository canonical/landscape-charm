import os.path

from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import ERROR

from lib.paths import default_paths


class HookError(Exception):
    """Raised by hooks when they want to fail.

    Raising this exception will make the hook process exit non-zero.
    """


class Hook(object):
    """Juju hook Abstraction, providing dependency injection for testing."""

    def __init__(self, hookenv=hookenv):
        """
        @param hookenv: The charm-helpers C{hookenv} module, will be replaced
            by tests.
        """
        self._hookenv = hookenv

    def __call__(self):
        """Invoke the hook.

        @return: An integer with the exit code for the hook.
        """
        self._hookenv.log("Invoke handler for %s" % self._hookenv.hook_name())
        try:
            self._run()
        except HookError, error:
            self._hookenv.log(str(error), ERROR)
            return 1
        return 0

    def _run(self):
        """Do the job."""
        raise NotImplementedError("Must be implemented by sub-classes")


class MaintenanceHook(Hook):
    """Hook that only runs when in maintenance mode."""

    def __init__(self, hookenv=hookenv, paths=default_paths):
        """
        @param hookenv: The charm-helpers C{hookenv} module, will be replaced
            by tests.
        @param paths: The landscape-server default paths class.
        """
        self._hookenv = hookenv
        self._paths = paths

    def __call__(self):
        """Invoke the hook.

        @return: An integer with the exit code for the hook.
        """
        if not os.path.exists(self._paths.maintenance_flag()):
            self._hookenv.action_fail(
                "This action can only be called on a unit in paused state.")
            return
        super(MaintenanceHook, self).__call__()
