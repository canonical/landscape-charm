import json
import os
import unittest

from helpers import EnvironmentFixture

CHARM_DIR = os.path.abspath(__file__)


class UnitStub(object):

    def __init__(self, public_address=None):
        self.info = {
            "public-address": public_address,
            "unit_name": "landscape-server/0"
        }
        self.commands = []

    def run(self, command):
        self.commands.append(command)
        return "", 0


class SentryStub(object):

    def __init__(self):
        self.unit = {
            "haproxy/0": UnitStub(public_address="1.2.3.4"),
            "landscape-server/0": UnitStub()
        }

    def wait(self, timeout):
        self.timeout = timeout


class DeploymentStub(object):

    deployed = False

    def __init__(self):
        self.sentry = SentryStub()

    def load(self, bundle):
        self.bundle = bundle
        self.services = bundle["landscape-test"]["services"]
        self.services["landscape-server"]["branch"] = CHARM_DIR

    def setup(self, timeout=None):
        self.deployed = True
        self.timeout = timeout


class SubprocessStub(object):
    """
    @ivar outputs: A dict mapping expected commands to their output.
    """

    def __init__(self):
        self.outputs = {}

    def check_output(self, command):
        output = self.outputs[" ".join(command)]
        if isinstance(output, list):
            return output.pop(0)
        else:
            return output


class NamedTemporaryFileStub(object):

    def __init__(self):
        self.name = "TEMP-FILE"


class TempfileStub(object):

    def __init__(self):
        self.NamedTemporaryFile = NamedTemporaryFileStub


class EnvironmentFixtureTest(unittest.TestCase):

    def setUp(self):
        super(EnvironmentFixtureTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.tempfile = TempfileStub()
        self.deployment = DeploymentStub()
        self.fixture = EnvironmentFixture(
            deployment=self.deployment, subprocess=self.subprocess,
            tempfile=self.tempfile)

    def test_setup(self):
        """
        The setup of the fixture triggers the deployment.
        """
        self.fixture.setUp()
        self.assertTrue(self.deployment.deployed)
        self.assertIn("landscape-test", self.deployment.bundle)
        self.assertEqual(3000, self.deployment.timeout)
        self.assertEqual(3000, self.deployment.sentry.timeout)
        config = self.deployment.services["landscape-server"]
        self.assertEqual("local:trusty/landscape-server", config["charm"])
        self.assertTrue(os.environ["JUJU_REPOSITORY"].startswith("/tmp"))

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
        unit = self.deployment.sentry.unit["landscape-server/0"]
        self.assertEqual(
            "sudo service landscape-appserver start", unit.commands[0])

    def test_stop_landscape_service_on_cleanup(self):
        """
        The stop_landscape_service method stops the requested service.
        """
        self.fixture.setUp()
        self.fixture.stop_landscape_service("landscape-appserver")
        unit = self.deployment.sentry.unit["landscape-server/0"]
        self.assertEqual(
            "sudo service landscape-appserver stop", unit.commands[0])
        self.fixture.cleanUp()
        self.assertEqual(
            "sudo service landscape-appserver start", unit.commands[1])

    def test_check_url(self):
        """
        The check_url method perform an HTTP request against the haproxy
        endpoint.
        """
        curl = "curl https://1.2.3.4/ -k -L -s --compressed"
        self.subprocess.outputs[curl] = b"hello"
        self.fixture.check_url("/", "hello")

    def test_check_url_with_proto(self):
        """
        The check_url method accepts a custom protocol.
        """
        curl = "curl http://1.2.3.4/ -k -L -s --compressed"
        self.subprocess.outputs[curl] = b"hello"
        self.fixture.check_url("/", "hello", proto="http")

    def test_check_url_with_post_data(self):
        """
        The check_url method can post data.
        """
        curl = "curl https://1.2.3.4/ -k -L -s --compressed -d foo"
        self.subprocess.outputs[curl] = b"hello"
        self.fixture.check_url("/", "hello", post_data="foo")

    def test_check_url_retry(self):
        """
        The check_url method retries two times before giving up.
        """
        curl = "curl https://1.2.3.4/ -k -L -s --compressed"
        self.subprocess.outputs[curl] = [b"foo", b"bar"]
        with self.assertRaises(AssertionError) as error:
            self.fixture.check_url("/", "hello", interval=0)
        message = str(error.exception)
        self.assertTrue(message.startswith("Content Not found!"))
        self.assertIn("good_content:['hello']", message)
        self.assertIn("output:bar", message)

    def test_login(self):
        """
        The check_url method can post data.
        """
        curl_index = (
            "curl https://1.2.3.4/ -k -L -s --compressed "
            "--cookie-jar TEMP-FILE -b TEMP-FILE")
        curl_login = (
            "curl https://1.2.3.4/redirect -k -L -s --compressed "
            "-d login.email=FOO&login.password=BAR&login=Login&"
            "form-security-token=f00 "
            "--cookie-jar TEMP-FILE -b TEMP-FILE")
        self.subprocess.outputs[curl_index] = (
            b'Access your account'
            b'<input type="hidden" name="form-security-token" value="f00"/>')
        self.subprocess.outputs[curl_login] = b'<h2>Organisation</h2> Success!'
        output = self.fixture.login("FOO", "BAR")
        self.assertIn('Success!', output)

    def test_bootstrap_landscape(self):
        """
        bootstrap_landscape method calls 'bootstrap' action on
        a landscape-server unit.
        """
        action_do_command = (
            "juju action do --format=json landscape-server/0 bootstrap "
            "admin-email=admin@example.com admin-name=foo admin-password=bar")
        self.subprocess.outputs[action_do_command] = json.dumps(
            {"Action queued with id": "17"}).encode("utf-8")
        action_fetch_command = "juju action fetch --format=json --wait 300 17"
        self.subprocess.outputs[action_fetch_command] = json.dumps(
            {"status": "fine"}).encode("utf-8")

        self.assertEqual(
            {"status": "fine"},
            self.fixture.bootstrap_landscape(
                admin_name="foo", admin_email="admin@example.com",
                admin_password="bar"))
