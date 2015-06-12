"""
Tests for the actions defined by the charm.
"""

import re

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
        index_page = self.environment.check_url("/", "Access your account")
        token_re = re.compile(
            '<input type="hidden" name="form-security-token" '
            'value="([0-9a-f-]*)"/>')
        token_match = token_re.search(index_page)
        self.assertTrue(bool(token_match))
        token = token_match.group(1)

        post_data = ("login.email=foo@bar&login.password=bar&login=Login"
                     "form-security-token=%s" % token)
        self.environment.check_url("/redirect", "foo", post_data=post_data)
