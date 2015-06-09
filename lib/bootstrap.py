import subprocess

from charmhelpers.core import hookenv

from lib.action import Action
from lib.paths import SCHEMA_SCRIPT


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

        self._subprocess.check_call(cmd)
