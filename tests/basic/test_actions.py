"""
Tests for the actions defined by the charm.
"""

from helpers import IntegrationTest
from layers import OneLandscapeUnitLayer, TwoLandscapeUnitsLayer


class ActionsTest(IntegrationTest):

    layer = OneLandscapeUnitLayer

    def test_pause_resume(self):
        """
        A landscape unit can be paused to stop all services and then
        resumed to start all services.
        """
        result = self.environment.pause_landscape()
        self.assertEqual("completed", result["status"])
        service_status = self.environment.get_landscape_services_status()
        # All Landcape services have been stopped
        self.assertEqual([], service_status["running"])
        self.assertTrue(len(service_status["stopped"]) > 0)

        result = self.environment.resume_landscape()
        self.assertEqual("completed", result["status"])
        service_status = self.environment.get_landscape_services_status()
        # All Landcape services have been started
        self.assertEqual([], service_status["stopped"])
        self.assertTrue(len(service_status["running"]) > 0)

    def test_resume_fail(self):
        """
        If some service fail to start, for example due to not migrating
        the schema after an upgrade, the 'resume' action will fail.

        After addressing the problems, it's possible to run the 'resume'
        action again.
        """
        self.environment.pause_landscape()
        self.addCleanup(self.environment.resume_landscape)
        remove_fake_db_patch = self.environment.add_fake_db_patch()
        self.addCleanup(remove_fake_db_patch)
        result = self.environment.resume_landscape()
        self.assertEqual("failed", result["status"])
        self.assertIn(
            "ERROR:root:main has unapplied patches", result["message"])
        #XXX: check that the unit status is in maintenance and 'Services
        #     stopped'. On xenial, this is no longer the case.

        remove_fake_db_patch()
        result = self.environment.resume_landscape()

    def test_bootstrap(self):
        """
        A landscape unit can be bootstrapped to create an admin account.
        """
        result = self.environment.bootstrap_landscape(
            admin_name="foo", admin_password="bar", admin_email="foo@bar")
        # This assumes that bootstrap has not run before (eg. in other tests).
        self.assertEqual("completed", result["status"])

        # Logging in should now work.
        self.environment.login("foo@bar", "bar")


class ActionsMultipleUnitsTest(IntegrationTest):

    layer = TwoLandscapeUnitsLayer

    def setUp(self):
        super(ActionsMultipleUnitsTest, self).setUp()
        [self.non_leader] = self.layer.non_leaders

    def test_non_leader_pause_resume(self):
        """
        The non-leader unit can be paused and later resumed.
        """
        result = self.environment.pause_landscape(unit=self.non_leader)
        self.assertEqual("completed", result["status"])

        result = self.environment.resume_landscape(unit=self.non_leader)
        self.assertEqual("completed", result["status"])
