from charmhelpers.core import hookenv

from lib.error import CharmError
from lib.hook import Hook
from lib.paths import default_paths


class Action(Hook):
    """Juju action abstraction, providing dependency injection for testing.

    @ivar required_status: The status the unit has to be in when the action
        is executed.
    """

    required_status = None

    def __call__(self):
        """
        Invoke the action's run() method.

        If _run() returns a value, set it using action_set().
        If _run() throws a CharmError, fail using action.fail().
        """
        if self.required_status is not None:
            status, _ = self._hookenv.status_get()
            if status != self.required_status:
                self._hookenv.action_fail(
                    "This action can only be called on a unit in status "
                    "'{}'.".format(self.required_status))
                return
        self._hookenv.log("Running action %s" % type(self).__name__)
        try:
            return_values = self._run()
            if return_values is not None:
                self._hookenv.action_set(return_values)
        except CharmError as error:
            self._hookenv.action_fail(str(error))


class MaintenanceAction(Action):
    """Action that only runs when in maintenance mode."""

    required_status = "maintenance"

    def __init__(self, hookenv=hookenv, paths=default_paths):
        """
        @param hookenv: The charm-helpers C{hookenv} module, will be replaced
            by tests.
        @param paths: The landscape-server default paths class.
        """
        self._hookenv = hookenv
        self._paths = paths
