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
        # All Landcape services and cron have been stopped
        self.assertEqual([], service_status["running"])
        self.assertTrue(len(service_status["stopped"]) > 0)
        self.assertFalse(
            self.environment.is_cron_running("landscape-server/0"))

        result = self.environment.resume_landscape()
        self.assertEqual("completed", result["status"])
        service_status = self.environment.get_landscape_services_status()
        # All Landcape services and cron have been started
        self.assertEqual([], service_status["stopped"])
        self.assertTrue(len(service_status["running"]) > 0)
        self.assertTrue(self.environment.is_cron_running("landscape-server/0"))
