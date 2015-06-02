import os

from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir
from lib.hook import MaintenanceHook


class DummyMaintenanceHook(MaintenanceHook):
    executed = False

    def _run(self):
        self.executed = True


class MaintenanceHookTest(HookenvTest):

    def setUp(self):
        super(MaintenanceHookTest, self).setUp()
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths

    def test_run(self):
        """Calling a dummy hook runs only with maintenance flag set."""

        open(self.paths.maintenance_flag(), "w")
        self.addCleanup(os.remove, self.paths.maintenance_flag())

        action = DummyMaintenanceHook(
            hookenv=self.hookenv, paths=self.paths)

        action()
        self.assertTrue(action.executed)

    def test_run_without_maintenance_flag(self):
        """
        When maintenance flag file is absent, maintenance hooks are no-ops.
        """
        action = DummyMaintenanceHook(
            hookenv=self.hookenv, paths=self.paths)

        action()
        self.assertFalse(action.executed)
        self.assertEqual(
            ["This action can only be called on a unit in paused state."],
            self.hookenv._action_fails)
