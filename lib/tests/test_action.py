import os

from lib.action import Action, MaintenanceAction
from lib.error import CharmError

from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir


class DummyAction(Action):
    executed = False

    def _run(self):
        self.executed = True


class DummyActionWithValues(Action):
    def _run(self):
        return {"key": "value"}


class DummyErrorAction(Action):
    def _run(self):
        raise CharmError("no go")


class ActionTest(HookenvTest):

    def setUp(self):
        super(ActionTest, self).setUp()
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths

    def test_run(self):
        """Calling an action executes the _run method."""
        action = DummyAction(hookenv=self.hookenv)
        action()
        self.assertTrue(action.executed)

    def test_run_with_return_values(self):
        """If _run returns values, they are set with action_set()."""
        action = DummyActionWithValues(hookenv=self.hookenv)
        action()
        self.assertEqual([{"key": "value"}], self.hookenv.action_sets)

    def test_run_raises_error(self):
        """
        If action fails with a CharmError, it is set as failed with the
        exception message as the error message.
        """
        action = DummyErrorAction(hookenv=self.hookenv)
        action()
        self.assertEqual(["no go"], self.hookenv.action_fails)


class DummyMaintenanceAction(MaintenanceAction):
    executed = False

    def _run(self):
        self.executed = True


class MaintenanceActionTest(HookenvTest):

    def setUp(self):
        super(MaintenanceActionTest, self).setUp()
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths

    def test_run(self):
        """Calling a dummy hook runs only with maintenance flag set."""

        open(self.paths.maintenance_flag(), "w")
        self.addCleanup(os.remove, self.paths.maintenance_flag())

        action = DummyMaintenanceAction(
            hookenv=self.hookenv, paths=self.paths)

        action()
        self.assertTrue(action.executed)

    def test_run_without_maintenance_flag(self):
        """
        When maintenance flag file is absent, maintenance hooks are no-ops.
        """
        action = DummyMaintenanceAction(
            hookenv=self.hookenv, paths=self.paths)

        action()
        self.assertFalse(action.executed)
        self.assertEqual(
            ["This action can only be called on a unit in paused state."],
            self.hookenv.action_fails)
