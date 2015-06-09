from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import ERROR

from lib.error import CharmError


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
        except CharmError as error:
            self._hookenv.log(str(error), ERROR)
            return 1
        return 0

    def _run(self):
        """Do the job."""
        raise NotImplementedError("Must be implemented by sub-classes")
