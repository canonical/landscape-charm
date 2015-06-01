import subprocess

from charmhelpers.core import hookenv

from lib.hook import MaintenanceHook
from lib.paths import SCHEMA_SCRIPT, default_paths


class MigrateSchemaAction(MaintenanceHook):
    """Execute schema upgrade action logic."""

    def __init__(self, hookenv=hookenv, paths=default_paths,
                 subprocess=subprocess):
        super(MigrateSchemaAction, self).__init__(hookenv=hookenv, paths=paths)
        self._subprocess = subprocess

    def _run(self):
        self._subprocess.check_call([SCHEMA_SCRIPT])
