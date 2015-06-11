from helpers import IntegrationTest
from layers import TwoLandscapeUnitsLayer


class LandscapeHATest(IntegrationTest):
    """Test HA aspects of Landscape server.

    The tests in here are intented to test that the haproxy config is
    correct, so that request gets routed to working units if some of the
    units go down.
    """

    layer = TwoLandscapeUnitsLayer

    def setUp(self):
        super(LandscapeHATest, self).setUp()
        self.leader = self.layer.leader
        [self.non_leader] = self.layer.non_leaders

    def test_app_leader_down(self):
        """
        Verify that the APP service is up when the leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-appserver", unit=self.leader)
        self.environment.check_service("appserver", attempts=25, interval=1)

    def test_app_non_leader_down(self):
        """
        Verify that the APP service is up when a non-leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-appserver", unit=self.non_leader)
        self.environment.check_service("appserver", attempts=25, interval=1)

    def test_msg_leader_down(self):
        """
        Verify that the MSG service is up when the leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-msgserver", unit=self.leader)
        self.environment.check_service("msgserver", attempts=25, interval=1)

    def test_msg_non_leader_down(self):
        """
        Verify that the MSG service is up when a non-leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-msgserver", unit=self.non_leader)
        self.environment.check_service("msgserver", attempts=25, interval=1)

    def test_ping_leader_down(self):
        """
        Verify that the PING service is up when the leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-pingserver", unit=self.leader)
        self.environment.check_service("pingserver", attempts=25, interval=1)

    def test_ping_non_leader_down(self):
        """
        Verify that the PING service is up when a non-leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-pingserver", unit=self.non_leader)
        self.environment.check_service("pingserver", attempts=25, interval=1)

    def test_api_leader_down(self):
        """
        Verify that the API service is up when the leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-api", unit=self.leader)
        self.environment.check_service("api", attempts=25, interval=1)

    def test_api_non_leader_down(self):
        """
        Verify that the API service is up when a non-leader unit goes down.
        """
        self.environment.stop_landscape_service(
            "landscape-api", unit=self.non_leader)
        self.environment.check_service("api", attempts=25, interval=1)

    def test_upload_leader_down(self):
        """
        If the leader goes down, the package upload service goes down as
        well. We don't have shared storage yet, so the package upload
        service is run on the leader only.
        """
        self.environment.stop_landscape_service(
            "landscape-package-upload", unit=self.leader)
        self.environment.check_service("package-upload", state="down")

    def test_upload_non_leader_down(self):
        """
        If a non-leader unit goes down, the package upload service goes
        continues to work, since the package upload service is running
        on the leader.
        """
        self.environment.stop_landscape_service(
            "landscape-package-upload", unit=self.non_leader)
        self.environment.check_service("package-upload")
