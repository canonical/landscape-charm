import subprocess

from charmhelpers.core.services.base import ManagerCallback

LSCTL = "/usr/bin/lsctl"
SCHEMA = "/usr/bin/landscape-schema"


class ScriptCallback(ManagerCallback):
    """Callback class for invoking Landscape scripts."""

    def __init__(self, subprocess=subprocess):
        self._subprocess = subprocess

    def _run(self, name, options=()):
        """Run the script with the given name and options."""
        command = [name]
        command += options
        self._subprocess.check_call(command)


class SchemaBootstrap(ScriptCallback):
    """Ensure that database users and schemas are setup.

    This will invoke the schema script with the --bootstrap flag.
    """
    def __call__(self, manager, service_name, event_name):
        self._run(SCHEMA, ("--bootstrap",))


class LSCtl(ScriptCallback):
    """Call the lsctl script to start or stop services."""

    def __call__(self, manager, service_name, event_name):
        action = event_name
        if event_name == "start":
            # XXX the 'start' event in the services framework is called after
            #     config changes have been applied and it's semantics actually
            #     maps to a 'restart' action.
            action = "restart"
        self._run(LSCTL, (action,))
