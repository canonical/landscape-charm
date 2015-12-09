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

    def test_run_valid_status(self):
        """
        If valid_status is set, the action will be executed if the
        current status is the same.
        """
        action = DummyAction(hookenv=self.hookenv)
        action.valid_status = "active"
        self.hookenv.status_set("active", "")
        action()
        self.assertTrue(action.executed)

    def test_run_invalid_status(self):
        """
        If valid_status is set, the action won't be executed if the
        current status is different.
        """
        action = DummyAction(hookenv=self.hookenv)
        action.valid_status = "active"
        self.hookenv.status_set("maintenance", "")
        action()
        self.assertFalse(action.executed)
        self.assertEqual(
            ["This action can only be called on a unit in status 'active'."],
            self.hookenv.action_fails)


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
        self.hookenv.status_set("maintenance", "")
        action = DummyMaintenanceAction(
            hookenv=self.hookenv, paths=self.paths)

        action()
        self.assertTrue(action.executed)

    def test_run_without_maintenance_status(self):
        """
        If the workload status isn't 'maintenance', the maintenance
        action won't be executed.
        """
        self.hookenv.status_set("active", "")
        action = DummyMaintenanceAction(
            hookenv=self.hookenv, paths=self.paths)

        action()
        self.assertFalse(action.executed)
        self.assertEqual(
            ["This action can only be called on a unit in status "
             "'maintenance'."],
            self.hookenv.action_fails)
