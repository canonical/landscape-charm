from lib.tests.helpers import HookenvTest
from lib.migrate_schema import MigrateSchemaAction
from lib.tests.stubs import SubprocessStub
from lib.paths import SCHEMA_SCRIPT


class MigrateSchemaActionTest(HookenvTest):

    def setUp(self):
        super(MigrateSchemaActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.action = MigrateSchemaAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The MigrateSchemaAction calls the schema script.
        """
        self.action()
        self.assertEqual([([SCHEMA_SCRIPT], {})], self.subprocess.calls)
