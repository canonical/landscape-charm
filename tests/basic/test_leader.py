from helpers import IntegrationTest
from layers import LandscapeLeaderDestroyedLayer
import unittest


class LandscapeLeaderDestroyedTest(IntegrationTest):
    """Test what happens when the landscape-server leader gets destroyed.

    The tests in here are intended to test that the newly elected leader
    takes over correctly.
    """

    layer = LandscapeLeaderDestroyedLayer

    def test_app(self):
        """
        Verify that the APP service is up after the leader unit is destroyed.
        """
        self.environment.check_service("appserver")

    def test_msg(self):
        """
        Verify that the MSG service is up after the leader unit is destroyed.
        """
        self.environment.check_service("msgserver")

    def test_ping(self):
        """
        Verify that the PING service is up after the leader unit is destroyed.
        """
        self.environment.check_service("pingserver")

    def test_api(self):
        """
        Verify that the API service is up after the leader unit is destroyed.
        """
        self.environment.check_service("api")

    def test_package_upload_new_leader(self):
        """
        Verify that the package upload service is now running on the new
        leader.

        package-upload is running only on the leader unit, and if a
        leader unit gets destroyed, the package-upload service is
        transferred to the new leader.
        """
        self.environment.check_service("package-upload")
