from charmhelpers.core import hookenv


class Hook(object):
    """Juju hook Abstraction, providing dependency injection for testing."""

    def __init__(self, log=hookenv.log, config=hookenv.config):
        self.log = log
        self.config = config

    def run(self):
        """Run the hook.

        @return: An integer with the exit code for the hook.
        """
        raise NotImplementedError("Must be implemented by sub-classes")
