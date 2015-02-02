import os
import subprocess

from charmhelpers.core.services.base import ManagerCallback

SCRIPTS_DIR = "/opt/canonical/landscape"


class ScriptCallback(ManagerCallback):
    """Callback class for invoking Landscape scripts."""

    def __init__(self, subprocess=subprocess, scripts_dir=SCRIPTS_DIR):
        self._subprocess = subprocess
        self._scripts_dir = scripts_dir

    def _run(self, name, options=()):
        """Run the script with the given name and options."""
        environment = os.environ.copy()
        # XXX Legacy environment variable, we should get rid of it when we
        #     complete converging our deployment methods.
        environment["LANDSCAPE_CONFIG"] = "standalone"
        command = [os.path.join(self._scripts_dir, name)]
        command += options
        self._subprocess.check_call(command, env=environment)


class SchemaBootstrap(ScriptCallback):
    """Ensure that database users and schemas are setup.

    This will invoke the schema script with the --bootstrap flag.
    """
    def __call__(self, manager, service_name, event_name):
        self._run("schema", ("--bootstrap",))
