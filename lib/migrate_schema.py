import subprocess

from charmhelpers.core import hookenv

from lib.hook import Hook
from lib.paths import SCHEMA_SCRIPT


class MigrateSchemaAction(Hook):
    """Execute schema upgrade action logic."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        self._subprocess = subprocess

        super(MigrateSchemaAction, self).__init__(hookenv=hookenv)

    def _run(self):
        self._subprocess.check_call([SCHEMA_SCRIPT])
