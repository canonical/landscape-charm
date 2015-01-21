from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import ERROR


class HookError(Exception):
    """Raised by hooks when they want to fail.

    Raising this exception will make the hook process exit non-zero.
    """


class Hook(object):
    """Juju hook Abstraction, providing dependency injection for testing."""

    _name = None  # MUST be set by sub-classes

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
        self._hookenv.log("Executing %s hook handler" % self._name)
        try:
            self._run()
        except HookError, error:
            self._hookenv.log(str(error), ERROR)
            return 1
        return 0

    def _run(self):
        """Do the job."""
        raise NotImplementedError("Must be implemented by sub-classes")
