import os.path

from charmhelpers.core import hookenv

from lib.hook import Hook, HookError
from lib.paths import default_paths


class ActionError(HookError):
    """Raised by actions when they want to fail.

    Raising this exception will make the action process exit with action_fail.
    """


class Action(Hook):
    """Juju action abstraction, providing dependency injection for testing."""

    def __call__(self):
        """
        Invoke the action's run() method.

        If _run() returns a value, set it using action_set().
        If _run() throws an ActionError, fail using action.fail().
        """
        self._hookenv.log("Running action %s" % type(self).__name__)
        try:
            return_values = self._run()
            if return_values is not None:
                self.set(return_values)
        except ActionError, error:
            self.fail(str(error))

    def fail(self, message):
        """Mark the action as failed with 'message'."""
        self._hookenv.action_fail(message)

    def set(self, values):
        """Set the action return values to 'values'."""
        self._hookenv.action_set(values)


class MaintenanceAction(Action):
    """Action that only runs when in maintenance mode."""

    def __init__(self, hookenv=hookenv, paths=default_paths):
        """
        @param hookenv: The charm-helpers C{hookenv} module, will be replaced
            by tests.
        @param paths: The landscape-server default paths class.
        """
        self._hookenv = hookenv
        self._paths = paths

    def __call__(self):
        """Invoke the action.

        @return: An integer with the exit code for the hook.
        """
        if not os.path.exists(self._paths.maintenance_flag()):
            self.fail(
                "This action can only be called on a unit in paused state.")
            return
        super(MaintenanceAction, self).__call__()
