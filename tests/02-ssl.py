#!/usr/bin/python3
"""SSL functional tests for the landscape-charm.

They are in a separate module because while bootstrapping a juju environment
takes time, this guarantees no side-effects introduced by other tests (SSL is
a charm config option).
"""
import base64
import logging
import os
import unittest

from fixtures import TestWithFixtures

from helpers import EnvironmentFixture, get_ssl_certificate

TEST_DIR = os.path.dirname(__file__)
CERT_FILE = os.path.join(TEST_DIR, "ssl", "server.crt")
KEY_FILE = os.path.join(TEST_DIR, "ssl", "server.key")


class OneLandscapeUnitTest(TestWithFixtures):

    def setUp(self):
        super(OneLandscapeUnitTest, self).setUp()
        with open(CERT_FILE, "rb") as fd:
            ssl_cert = fd.read()
        with open(KEY_FILE, "rb") as fd:
            ssl_key = fd.read()
        config = {
            "landscape": {
                "ssl-cert": base64.b64encode(ssl_cert).decode("utf-8"),
                "ssl-key": base64.b64encode(ssl_key).decode("utf-8")}}
        self.environment = self.useFixture(EnvironmentFixture(config=config))

    def test_certificate_is_what_we_expect(self):
        """
        The SSL certificate we get from the server is the one we set as a
        fixture during environment initialization.
        """
        endpoint = "%s:443" % self.environment.get_haproxy_public_address()
        with open(CERT_FILE, "r") as fd:
            ssl_cert = fd.read().rstrip()
        self.assertEqual(ssl_cert, get_ssl_certificate(endpoint))


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(OneLandscapeUnitTest))
    return suite


if __name__ == "__main__":
    logging.basicConfig(
        level='DEBUG', format='%(asctime)s %(levelname)s %(message)s')
    unittest.main(verbosity=2)
