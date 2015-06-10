"""
Tests for the actions defined by the charm.
"""

from helpers import IntegrationTest
from layers import OneLandscapeUnitLayer


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

    def test_bootstrap(self):
        """
        A landscape unit can be bootstrapped to create an admin account.
        """
        result = self.environment.bootstrap_landscape(
            admin_name="foo", admin_password="bar", admin_email="foo@bar")
        self.assertEqual("completed", result["status"])
        # This phrase should match the login form and not match the
        # new-standalone-user form.
        self.environment.check_url("/", "Access your account")
        #self.environment.check_url(
        #    "/", "foo",
        #    post_data="login.email=foo@bar&login.password=bar")
