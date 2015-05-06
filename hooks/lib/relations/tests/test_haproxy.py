import base64
import yaml

from fixtures import TempDir

from lib.relations.haproxy import (
    HAProxyProvider, HAProxyRequirer, SERVER_OPTIONS, ERRORFILES_MAP)
from lib.hook import HookError
from lib.tests.helpers import HookenvTest
from lib.tests.offline_fixture import OfflineDir
from lib.tests.sample import SAMPLE_SERVICE_COUNT_DATA

HTTPS_INDEX = 1


class HAProxyProviderTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(HAProxyProviderTest, self).setUp()
        self.offline_dir = self.useFixture(OfflineDir()).path

    def test_required_keys(self):
        """
        The HAProxyProvider class defines all keys that are required to
        be set on the db relation in order for the relation to be considered
        ready.
        """
        self.assertEqual(
            ["services"], HAProxyProvider.required_keys)

    def test_provide_data(self):
        """
        The HAProxyProvider class feeds haproxy with the services that this
        Landscape unit runs. By default all services are run.
        """
        relation = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=self.offline_dir)

        # Provide some fake ssl-cert and ssl-key config entries
        config = self.hookenv.config()
        config["ssl-cert"] = base64.b64encode("a cert")
        config["ssl-key"] = base64.b64encode("a key")

        expected_certs = [base64.b64encode("a cert\na key")]

        # We expect errorfiles to be set.
        expected_errorfiles = []
        for error_code, filename in sorted(ERRORFILES_MAP.items()):
            expected_content = base64.b64encode("Fake %s" % filename)
            expected_errorfiles.append(
                {"http_status": error_code, "content": expected_content})

        data = relation.provide_data()

        services = yaml.safe_load(data["services"])
        self.assertEqual([
            {"service_name": "landscape-http",
             "service_host": "0.0.0.0",
             "service_port": 80,
             "service_options": [
                 "mode http",
                 "balance leastconn",
                 "option httpchk HEAD / HTTP/1.0",
                 "acl ping path_beg -i /ping",
                 "redirect scheme https unless ping",
                 "use_backend landscape-ping if ping"],
             "errorfiles": expected_errorfiles,
             "servers": [
                 ["landscape-appserver-landscape-server-0",
                  "1.2.3.4", 8080, SERVER_OPTIONS]],
             "backends": [
                 {"backend_name": "landscape-ping",
                  "servers": [
                      ["landscape-pingserver-landscape-server-0-0",
                       "1.2.3.4", 8070, SERVER_OPTIONS],
                      ["landscape-pingserver-landscape-server-0-1",
                       "1.2.3.4", 8071, SERVER_OPTIONS]]}]},
            {"service_name": "landscape-https",
             "service_host": "0.0.0.0",
             "service_port": 443,
             "service_options": [
                 "mode http",
                 "balance leastconn",
                 "option httpchk HEAD / HTTP/1.0",
                 "http-request set-header X-Forwarded-Proto https",
                 "acl message path_beg -i /message-system",
                 "acl api path_beg -i /api",
                 "use_backend landscape-message if message",
                 "use_backend landscape-api if api"],
             "errorfiles": expected_errorfiles,
             "crts": expected_certs,
             "servers": [
                 ["landscape-appserver-landscape-server-0",
                  "1.2.3.4", 8080, SERVER_OPTIONS]],
             "backends": [
                 {"backend_name": "landscape-message",
                  "servers": [
                      ["landscape-message-server-landscape-server-0-0",
                       "1.2.3.4", 8090, SERVER_OPTIONS],
                      ["landscape-message-server-landscape-server-0-1",
                       "1.2.3.4", 8091, SERVER_OPTIONS]]},
                 {"backend_name": "landscape-api",
                  "servers": [
                      ["landscape-api-landscape-server-0",
                       "1.2.3.4", 9080, SERVER_OPTIONS]]}]}],
            services)

    def test_files_cannot_be_read(self):
        """
        In case a file specified in the errorfiles map cannot be read, the
        provide_data method raises a HookError.
        """
        offline_dir = self.useFixture(TempDir()).path
        provider = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=offline_dir)

        self.assertRaises(HookError, provider.provide_data)

    def test_default_ssl_cert_is_used_without_config_keys(self):
        """
        If no "ssl-cert" is specified, the provide_data method returns
        ["DEFAULT"] for the HAproxy SSL cert.
        """
        provider = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=self.offline_dir)
        data = provider.provide_data()
        services = yaml.safe_load(data["services"])

        https_service = services[HTTPS_INDEX]

        self.assertEqual(["DEFAULT"], https_service["crts"])

    def test_cert_and_key_pem_is_used_when_passed_cert_and_key_config(self):
        """
        When passed both a cert and a key config, the provide_data method
        returns the equivalent pem in the HAproxy SSL cert relation setting.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = base64.b64encode("a cert")
        config["ssl-key"] = base64.b64encode("a key")
        provider = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=self.offline_dir,
            hookenv=self.hookenv)

        data = provider.provide_data()
        services = yaml.safe_load(data["services"])

        https_service = services[HTTPS_INDEX]

        expected = "a cert\na key"
        decoded_result = base64.b64decode(https_service["crts"][0])
        self.assertEqual(expected, decoded_result)

    def test_provide_data_raises_hookerror_for_invalid_b64_cert(self):
        """
        When passed a cert that is not valid b64, the provide_data method
        raises a HookError.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = "a cert"  # Not b64 encoded!
        config["ssl-key"] = base64.b64encode("a key")

        provider = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=self.offline_dir,
            hookenv=self.hookenv)

        expected = (
            "The supplied 'ssl-cert' or 'ssl-key' parameter is not valid"
            " base64.")

        with self.assertRaises(HookError) as error:
            provider.provide_data()
        self.assertEqual(expected, str(error.exception))

    def test_provide_data_raises_hookerror_for_invalid_b64_key(self):
        """
        When passed a key that is not valid b64, the provide_data method
        raises a HookError.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = base64.b64encode("a cert")
        config["ssl-key"] = "something"  # Not base64 encoded!

        provider = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=self.offline_dir,
            hookenv=self.hookenv)

        expected = (
            "The supplied 'ssl-cert' or 'ssl-key' parameter is not valid"
            " base64.")

        with self.assertRaises(HookError) as error:
            provider.provide_data()
        self.assertEqual(expected, str(error.exception))

    def test_provide_data_raises_hookerror_for_missing_key(self):
        """
        When an ssl-cert config key is present but no ssl-key was specified,
        the provide_data method raises a HookError.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = base64.b64encode("a cert")
        # Not setting 'ssl-key'
        provider = HAProxyProvider(
            SAMPLE_SERVICE_COUNT_DATA, offline_dir=self.offline_dir,
            hookenv=self.hookenv)

        expected = "'ssl-cert' is specified but 'ssl-key' is missing!"

        with self.assertRaises(HookError) as error:
            provider.provide_data()
        self.assertEqual(expected, str(error.exception))


class HAProxyRequirerTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The HAProxyRequirer class defines all keys that are required to
        be set on the db relation in order for the relation to be considered
        ready.
        """
        self.assertEqual(
            ["public-address", "ssl_cert"], HAProxyRequirer.required_keys)
