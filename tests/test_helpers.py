from unittest import TestCase

from helpers import EnvironmentFixture


class UnitStub(object):

    def __init__(self, public_address=None):
        self.info = {
            "public-address": public_address
        }
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        return "", 0


class SentryStub(object):

    def __init__(self):
        self.unit = {
            "haproxy/0": UnitStub(public_address="1.2.3.4"),
            "landscape/0": UnitStub()
        }

    def wait(self, timeout):
        self.timeout = timeout


class DeploymentStub(object):

    deployed = False

    def __init__(self):
        self.sentry = SentryStub()

    def load(self, bundle):
        self.bundle = bundle

    def setup(self, timeout=None):
        self.deployed = True
        self.timeout = timeout


class EnvironmentFixtureTest(TestCase):

    def setUp(self):
        super(EnvironmentFixtureTest, self).setUp()
        self.deployment = DeploymentStub()
        self.fixture = EnvironmentFixture(deployment=self.deployment)

    def test_setup(self):
        """
        The setup of the fixture triggers the deployment.
        """
        self.fixture.setUp()
        self.assertTrue(self.deployment.deployed)
        self.assertIn("landscape-test", self.deployment.bundle)
        self.assertEqual(1500, self.deployment.timeout)
        self.assertEqual(1500, self.deployment.sentry.timeout)

    def test_get_haproxy_public_address(self):
        """
        The get_haproxy_public_address method returns the address of the
        given haproxy unit.
        """
        self.assertEqual("1.2.3.4", self.fixture.get_haproxy_public_address())

    def test_start_landscape_service(self):
        """
        The start_landscape_service method starts the requested service.
        """
        self.fixture.start_landscape_service("landscape-appserver")
        unit = self.deployment.sentry.unit["landscape/0"]
        self.assertEqual(
            "sudo service landscape-appserver start", unit.commands[0])

    def test_stop_landscape_service_on_cleanup(self):
        """
        The stop_landscape_service method stops the requested service.
        """
        self.fixture.stop_landscape_service("landscape-appserver")
        unit = self.deployment.sentry.unit["landscape/0"]
        self.assertEqual(
            "sudo service landscape-appserver stop", unit.commands[0])
