#!/usr/bin/python3
"""
SSL functional tests for the landscape-charm.

They are in a separate module because while bootstrapping a juju environment
takes time, this guarantees no side-effects introduced by other tests (SSL is
a charm config option).
"""
import base64
import jujulib.deployer
import logging
import os
import subprocess
import unittest

from glob import glob
from os import getenv
from os.path import dirname, abspath, join, exists

from helpers import juju_status, find_address, check_url, BaseLandscapeTests


log = logging.getLogger(__file__)

CHARM_DIR = dirname(dirname(abspath(__file__)))

CONFIG_CERT_FILE = join(CHARM_DIR, "config", "ssl-cert")
CONFIG_KEY_FILE = join(CHARM_DIR, "config", "ssl-key")


def setUpModule():
    """Deploys Landscape via the charm. All the tests use this deployment."""
    deployer = jujulib.deployer.Deployer()

    # Copy the fixture base64 encoded certificate and key to the right place in
    # the config directory.

    if not exists(CONFIG_CERT_FILE):
        subprocess.check_call(
            ["cp", join(CHARM_DIR, "tests", "ssl", "server.crt.base64"),
             CONFIG_CERT_FILE])

    if not exists(CONFIG_KEY_FILE):
        subprocess.check_call(
            ["cp", join(CHARM_DIR, "tests", "ssl", "server.key.base64"),
             CONFIG_KEY_FILE])

    # Grab the bundles and actually deploy the environment.
    bundles = glob(join(CHARM_DIR, "bundles", "*.yaml"))
    deployer.deploy(getenv("DEPLOYER_TARGET", "landscape-scalable"), bundles,
                    timeout=3000)

    frontend = find_address(juju_status(), "haproxy")

    # Make sure the app server is up.
    # Note: In order to work on a new server or a server with the
    #       first admin user already created, this phrase should match
    #       the new-standalone-user form, the login form, and not
    #       the maintenance page.
    good_content = "passphrase"
    log.info("Polling. Waiting for app server: {}".format(frontend))
    check_url("https://{}/".format(frontend), good_content, interval=30,
              attempts=10, retry_unavailable=True)


class LandscapeSSLTests(BaseLandscapeTests):

    @classmethod
    def setUpClass(cls):
        """Prepares juju_status which many tests use."""
        cls.juju_status = juju_status()
        cls.frontend = find_address(cls.juju_status, "haproxy")

    def _strip_certificate(self, certificate):
        """
        A helper to get just the certificate froma string, without headers.
        A regex might be nicer, but this works and is easy to read.
        """
        certificate = certificate.split("BEGIN CERTIFICATE-----")[1]
        certificate = certificate.split("-----END CERTIFICATE")[0]
        certificate = certificate.replace("\n", "")
        return certificate

    def test_certificate_is_what_we_expect(self):
        """
        The SSL certificate we get from the server is the one we set as a
        fixture during environment initialization.
        """
        url = "%s:443" % self.frontend

        # Call openssl s_client connect to get the actual certificate served.
        # The command line program is a bit arcahic and therefore we need
        # to do a few things like send it a newline char (a user "return"), and
        # filter some of the output (it print non-error messages on stderr).
        ps = subprocess.Popen(('echo', '-n'), stdout=subprocess.PIPE)
        with open(os.devnull, 'w') as dev_null:
            output = subprocess.check_output(  # output is bytes
                ['openssl', 's_client', '-connect', url],
                stdin=ps.stdout, stderr=dev_null)
        ps.stdout.close()  # Close the pipe fd
        ps.wait()  # This closes the subprocess sending the newline.

        obtained_certificate = self._strip_certificate(output.decode("utf-8"))

        expected_crt = None
        # Use the base64 encoded version as a reference in case it's not the
        # fixtures one but a real cert.
        with open(CONFIG_CERT_FILE, "r") as fd:
            expected_crt = fd.read()

        expected_crt = base64.b64decode(expected_crt)  # expected_crt is bytes
        expected_crt = self._strip_certificate(expected_crt.decode("utf-8"))

        self.assertEqual(expected_crt, obtained_certificate)


if __name__ == "__main__":
    logging.basicConfig(
        level='DEBUG', format='%(asctime)s %(levelname)s %(message)s')
    unittest.main(verbosity=2)
