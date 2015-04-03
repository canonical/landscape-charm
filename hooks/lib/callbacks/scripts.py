import os
import subprocess

from charmhelpers.core.services.base import ManagerCallback

LSCTL = "/usr/bin/lsctl"
SCHEMA = "/usr/bin/landscape-schema"
SHELL = "/bin/sh"

CONFIGS_DIR = "/opt/canonical/landscape/configs"
STANDALONE_DIR = os.path.join(CONFIGS_DIR, "standalone")


class ScriptCallback(ManagerCallback):
    """Callback class for invoking Landscape scripts."""

    def __init__(self, subprocess=subprocess):
        self._subprocess = subprocess

    def _run(self, name, options=()):
        """Run the script with the given name and options."""
        command = [name]
        command += options
        self._subprocess.check_call(command)


class EnsureConfigDir(ScriptCallback):
    """Ensure that the config dir for the configured deployment mode exists.

    XXX This is a temporary workaround till we'll make the Landscape server
        code always look at the common same location for configuration files.
    """
    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)

        # Lookup the deployment mode
        for data in service.get("required_data"):
            if "hosted" in data:
                deployment_mode = data["hosted"][0]["deployment-mode"]
                break

        # Create a symlink for the config directory
        config_link = os.path.join(CONFIGS_DIR, deployment_mode)
        self._run(
            SHELL, ("-c", "if ! [ -e %s ]; then ln -s %s %s; fi" % (
                config_link, STANDALONE_DIR, config_link)))


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
            #     config changes have been applied and its semantics actually
            #     maps to a 'restart' action.
            action = "restart"
        self._run(LSCTL, (action,))
