import json
import subprocess

from charmhelpers.core import hookenv

from lib.action import Action
from lib.paths import API_SCRIPT


class BootstrapAction(Action):
    """Action to bootstrap Landscape and create an initial admin user."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        super(BootstrapAction, self).__init__(hookenv=hookenv)
        self._subprocess = subprocess

    def _run(self):
        admin_name = self._hookenv.action_get("admin-name")
        admin_email = self._hookenv.action_get("admin-email")
        admin_password = self._hookenv.action_get("admin-password")
        registration_key = self._hookenv.action_get("registration-key")

        environment = {
            "LANDSCAPE_API_KEY": "anonymous",
            "LANDSCAPE_API_SECRET": "anonymous",
            "LANDSCAPE_API_URI": "http://localhost:9080/api/",
        }
        cmd = [
            API_SCRIPT, "call", "BootstrapLDS", "--json",
            "admin_name={}".format(admin_name),
            "admin_email={}".format(admin_email),
            "admin_password={}".format(admin_password)]
        if registration_key:
            cmd.append("registration_key={}".format(registration_key))

        output = self._subprocess.check_output(cmd, env=environment)
        key, secret = self._parse_schema_output(output)
        result = {"api-credentials": {"key": key, "secret": secret}}

        self._hookenv.action_set(result)

    def _parse_schema_output(self, output):
        """Extract API credentials from the schema bootstrap output."""
        credentials = json.loads(output)
        key = credentials.get("LANDSCAPE_API_KEY")
        secret = credentials.get("LANDSCAPE_API_SECRET")
        return key, secret
