"""SSL functional tests for the landscape-charm.

They are in a separate module because while bootstrapping a juju environment
takes time, this guarantees no side-effects introduced by other tests (SSL is
a charm config option).
"""

from sslcert.assets import CERT_FILE
from helpers import IntegrationTest, OneLandscapeUnitLayer


class SSLConfigurationTest(IntegrationTest):

    layer = OneLandscapeUnitLayer

    def test_certificate_is_what_we_expect(self):
        """
        The SSL certificate we get from the server is the one we set as a
        fixture during environment initialization.
        """
        with open(CERT_FILE, "r") as fd:
            ssl_cert = fd.read().rstrip()
        self.assertEqual(ssl_cert, self.environment.get_haproxy_certificate())
