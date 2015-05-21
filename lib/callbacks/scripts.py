import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ManagerCallback

from lib.paths import LSCTL, SCHEMA_SCRIPT


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
        self._run(SCHEMA_SCRIPT, ("--bootstrap",))


class LSCtl(ScriptCallback):
    """Call the lsctl script to start or stop services."""

    def __init__(self, subprocess=subprocess, hookenv=hookenv):
        super(LSCtl, self).__init__(subprocess=subprocess)
        self._hookenv = hookenv

    def __call__(self, manager, service_name, event_name):
        action = event_name
        if event_name == "start":
            # XXX the 'start' event in the services framework is called after
            #     config changes have been applied and its semantics actually
            #     maps to a 'restart' action.
            action = "restart"

        # In case we're reacting to config changes, we don't always want to
        # restart the processes (for example if only the APT source changed).
        if self._hookenv.hook_name() == "config-changed":
            config = self._hookenv.config()
            changed = set()
            for key in config.keys():
                if config.changed(key):
                    changed.add(key)
            if changed.issubset({"source", "key"}):
                return

        self._run(LSCTL, (action,))
