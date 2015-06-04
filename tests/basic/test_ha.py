"""
"""

from helpers import IntegrationTest
from layers import TwoLandscapeUnitsLayer


class LandscapeHATest(IntegrationTest):

    layer = TwoLandscapeUnitsLayer

    def test_app(self):
        """Verify that the APP service is up.

        Specifically that it is reachable and that it presents the new
        user form.

        Note: In order to work on a new server or a server with the
          first admin user already created, this phrase should match
          the new-standalone-user form, the login form, and not
          the maintenance page.
        """
        self.environment.pause_landscape(unit=0)
        self.addCleanup(self.environment.resume_landscape, unit=0)
        self.environment.check_url("/", "passphrase")
