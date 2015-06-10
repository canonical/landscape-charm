from helpers import IntegrationTest
from layers import LandscapeLeaderDestroyedLayer


class LandscapeLeaderDestroyedTest(IntegrationTest):
    """Test what happens when the landscape-server leader gets destroyed.

    The tests in here are intented to test that the newly elected leader
    takes over correctly.
    """

    layer = LandscapeLeaderDestroyedLayer

    def test_package_upload_new_leader(self):
        self.environment.check_service("package-upload")
