import subprocess

from charmhelpers.core import hookenv

from lib.action import Action
from lib.paths import SCHEMA_SCRIPT

CREDENTIALS_MARKER = "API credentials:"


class BootstrapAction(Action):
    """Action to bootstrap Landscape and create an initial admin user."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        super(BootstrapAction, self).__init__(hookenv=hookenv)
        self._subprocess = subprocess

    def _run(self):
        admin_name = self._hookenv.action_get("admin-name")
        admin_email = self._hookenv.action_get("admin-email")
        admin_password = self._hookenv.action_get("admin-password")

        cmd = (SCHEMA_SCRIPT, "--create-lds-account-only", "--admin-name",
               admin_name, "--admin-email", admin_email,
               "--admin-password", admin_password)

        output = self._subprocess.check_output(cmd)
        key, secret = self._parse_schema_output(output)
        result = {"api-credentials": {"key": key, "secret": secret}}

        self._hookenv.action_set(result)

    def _parse_schema_output(self, output):
        """Extract API credentials from the schema bootstrap output."""
        key = None
        secret = None
        for line in output.split("\n"):
            if line.startswith(CREDENTIALS_MARKER):
                line = line[len(CREDENTIALS_MARKER) + 1:]
                key, secret = line.split(" ")[2:4]
        return key, secret
