from lib.migrate_schema import MigrateSchemaAction
from lib.paths import SCHEMA_SCRIPT
from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir
from lib.tests.stubs import SubprocessStub


class MigrateSchemaActionTest(HookenvTest):

    def setUp(self):
        super(MigrateSchemaActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths

    def test_run(self):
        """
        The MigrateSchemaAction calls the schema script.
        """
        self.hookenv.status_set("maintenance", "")

        action = MigrateSchemaAction(
            hookenv=self.hookenv, paths=self.paths, subprocess=self.subprocess)
        action()
        self.assertEqual([([SCHEMA_SCRIPT], {})], self.subprocess.calls)

    def test_run_without_maintenance_flag(self):
        """
        The MigrateSchemaAction doesn't call the schema script if the
        unit is in an 'active' state.
        """
        self.hookenv.status_set("active", "")

        action = MigrateSchemaAction(
            hookenv=self.hookenv, paths=self.paths, subprocess=self.subprocess)
        action()
        self.assertEqual([], self.subprocess.calls)
