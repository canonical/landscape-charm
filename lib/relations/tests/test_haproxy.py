import base64
import os
import yaml

from fixtures import TempDir

from lib.relations.config import ConfigRequirer
from lib.relations.haproxy import (
    HAProxyProvider, HAProxyRequirer, SERVER_OPTIONS, ERRORFILES_MAP,
    SSLCertificateKeyMissingError, SSLCertificateInvalidDataError,
    ErrorFilesConfigurationError)
from lib.paths import Paths
from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir

HTTPS_INDEX = 1


class HAProxyProviderTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(HAProxyProviderTest, self).setUp()
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths
        self.config_requirer = ConfigRequirer(hookenv=self.hookenv)
        self.hosted_requirer = {}

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
        self.hookenv.leader = False
        self.hookenv.config().update({"worker-counts": 2})
        config_requirer = ConfigRequirer(hookenv=self.hookenv)
        self.config_requirer["config"]["worker-counts"] = 2
        relation = HAProxyProvider(
            config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

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
                 "timeout client 300000",
                 "timeout server 300000",
                 "balance leastconn",
                 "option httpchk HEAD / HTTP/1.0",
                 "acl ping path_beg -i /ping",
                 "acl repository path_beg -i /repository",
                 "redirect scheme https unless ping OR repository",
                 "use_backend landscape-ping if ping"],
             "errorfiles": expected_errorfiles,
             "servers": [
                 ["landscape-appserver-landscape-server-0-0",
                  "1.2.3.4", 8080, SERVER_OPTIONS],
                 ["landscape-appserver-landscape-server-0-1",
                  "1.2.3.4", 8081, SERVER_OPTIONS]],
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
                 "timeout client 300000",
                 "timeout server 300000",
                 "balance leastconn",
                 "option httpchk HEAD / HTTP/1.0",
                 "http-request set-header X-Forwarded-Proto https",
                 "acl message path_beg -i /message-system",
                 "acl attachment path_beg -i /attachment",
                 "acl api path_beg -i /api",
                 "acl prometheus_metrics path_beg -i /metrics",
                 "http-request deny if prometheus_metrics",
                 "use_backend landscape-message if message",
                 "use_backend landscape-message if attachment",
                 "use_backend landscape-api if api"],
             "errorfiles": expected_errorfiles,
             "crts": expected_certs,
             "servers": [
                 ["landscape-appserver-landscape-server-0-0",
                  "1.2.3.4", 8080, SERVER_OPTIONS],
                 ["landscape-appserver-landscape-server-0-1",
                  "1.2.3.4", 8081, SERVER_OPTIONS]],
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

    def test_provide_data_error_files(self):
        """
        Error pages from the Landscape offline dir gets set as error
        pages for 403, 500, 502, 503 and 504.
        """
        error_files = {
            "403": "unauthorized-haproxy.html",
            "500": "exception-haproxy.html",
            "502": "unplanned-offline-haproxy.html",
            "503": "unplanned-offline-haproxy.html",
            "504": "timeout-haproxy.html"
            }
        for code, name in error_files.items():
            with open(os.path.join(self.paths.offline_dir(), name), "w") as fd:
                fd.write("{} error page".format(name))

        relation = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = relation.provide_data()
        services = yaml.safe_load(data["services"])
        landscape_http, landscape_https = services

        error_pages = [
            {"http_status": code,
             "content": "{} error page".format(name).encode("base64").strip()}
            for code, name in error_files.items()]
        self.assertItemsEqual(error_pages, landscape_http["errorfiles"])
        self.assertItemsEqual(error_pages, landscape_https["errorfiles"])

    def test_files_cannot_be_read(self):
        """
        In case a file specified in the errorfiles map cannot be read, the
        provide_data method raises an ErrorFilesConfigurationError.
        """
        # Create an empty root tree
        temp_dir = self.useFixture(TempDir())
        provider = HAProxyProvider(
            self.config_requirer, self.hosted_requirer,
            paths=Paths(temp_dir.path), hookenv=self.hookenv)

        self.assertRaises(ErrorFilesConfigurationError, provider.provide_data)

    def test_provide_data_package_upload_leader(self):
        """
        If the unit is a leader, package-upload config is provided for
        the https service, but not for http.
        """
        self.hookenv.leader = True
        relation = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = relation.provide_data()

        [http, https] = yaml.safe_load(data["services"])
        self.assertNotIn(
            "acl package-upload path_beg -i /upload",
            http["service_options"])
        self.assertNotIn(
            "use_backend landscape-package-upload if package-upload",
            http["service_options"])
        self.assertNotIn(
            "landscape-package-upload",
            [backend["backend_name"] for backend in http["backends"]])
        self.assertIn(
            "acl package-upload path_beg -i /upload",
            https["service_options"])
        self.assertIn(
            "use_backend landscape-package-upload if package-upload",
            https["service_options"])
        self.assertIn(
            "landscape-package-upload",
            [backend["backend_name"] for backend in https["backends"]])

    def test_provide_data_package_upload_no_leader(self):
        """
        If the unit is not a leader, package-upload config isn't
        provided for neither the https nor http services.
        """
        self.hookenv.leader = False
        relation = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = relation.provide_data()

        [http, https] = yaml.safe_load(data["services"])
        self.assertNotIn(
            "acl package-upload path_beg -i /upload",
            http["service_options"])
        self.assertNotIn(
            "use_backend landscape-package-upload if package-upload",
            http["service_options"])
        self.assertNotIn(
            "landscape-package-upload",
            [backend["backend_name"] for backend in http["backends"]])
        self.assertNotIn(
            "acl package-upload path_beg -i /upload",
            https["service_options"])
        self.assertNotIn(
            "use_backend landscape-package-upload if package-upload",
            https["service_options"])
        self.assertNotIn(
            "landscape-package-upload",
            [backend["backend_name"] for backend in https["backends"]])

    def test_default_ssl_cert_is_used_without_config_keys(self):
        """
        If no "ssl-cert" is specified, the provide_data method returns
        ["DEFAULT"] for the HAproxy SSL cert.
        """
        provider = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)
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
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = provider.provide_data()
        services = yaml.safe_load(data["services"])

        https_service = services[HTTPS_INDEX]

        expected = "a cert\na key"
        decoded_result = base64.b64decode(https_service["crts"][0])
        self.assertEqual(expected, decoded_result)

    def test_provide_data_raises_sslerror_for_invalid_b64_cert(self):
        """
        When passed a cert that is not valid b64, the provide_data method
        raises a SSLCertificateInvalidDataError.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = "a cert"  # Not b64 encoded!
        config["ssl-key"] = base64.b64encode("a key")

        provider = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        expected = (
            "The supplied 'ssl-cert' or 'ssl-key' parameters are not valid"
            " base64.")

        with self.assertRaises(SSLCertificateInvalidDataError) as error:
            provider.provide_data()
        self.assertEqual(expected, str(error.exception))

    def test_provide_data_raises_sslerror_for_invalid_b64_key(self):
        """
        When passed a key that is not valid b64, the provide_data method
        raises a SSLCertificateInvalidDataError.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = base64.b64encode("a cert")
        config["ssl-key"] = "something"  # Not base64 encoded!

        provider = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        expected = (
            "The supplied 'ssl-cert' or 'ssl-key' parameters are not valid"
            " base64.")

        with self.assertRaises(SSLCertificateInvalidDataError) as error:
            provider.provide_data()
        self.assertEqual(expected, str(error.exception))

    def test_provide_data_raises_sslerror_for_missing_key(self):
        """
        When an ssl-cert config key is present but no ssl-key was specified,
        the provide_data method raises a SSLCertificateKeyMissingError.
        """
        config = self.hookenv.config()
        config["ssl-cert"] = base64.b64encode("a cert")
        # Not setting 'ssl-key'
        provider = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        expected = "'ssl-cert' is specified but 'ssl-key' is missing!"

        with self.assertRaises(SSLCertificateKeyMissingError) as error:
            provider.provide_data()
        self.assertEqual(expected, str(error.exception))

    def test_leader_has_package_upload_backend(self):
        """
        The landscape service leader writes a server entry in the
        landscape-package-upload backend.
        """
        self.hookenv.leader = True
        provider = HAProxyProvider(
            self.config_requirer, self.hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = provider.provide_data()
        services = yaml.safe_load(data["services"])

        https_service = services[HTTPS_INDEX]
        backends = https_service["backends"]

        # "/upload" is stripped from URLs before being forwarded to
        # the package-upload backend.
        self.assertIn(
            "reqrep ^([^\\ ]*)\\ /upload/(.*) \\1\ /\\2",
            https_service["service_options"])

        package_upload = None
        for backend in backends:
            if backend["backend_name"] == "landscape-package-upload":
                package_upload = backend

        self.assertIsNotNone(package_upload)
        self.assertEqual(1, len(package_upload["servers"]))
        expected = [
            'landscape-package-upload-landscape-server-0', '1.2.3.4', 9100,
            ['check', 'inter 5000', 'rise 2', 'fall 5', 'maxconn 50']]
        self.assertEqual(expected, package_upload["servers"][0])

    def test_provide_data_without_pppa_proxy(self):
        """
        When HostedProvider only specifies deployment-mode, that means that
        there is not really a hosted relation, thus pppa-proxy should not be
        configured.
        """
        self.hookenv.leader = False
        hosted_data = []
        hosted_requirer = {"hosted": hosted_data}
        relation = HAProxyProvider(
            self.config_requirer, hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = relation.provide_data()

        services = yaml.safe_load(data["services"])
        https_service = services[1]
        service_options = https_service["service_options"]
        self.assertNotIn(
            "acl pppa-proxy path_beg -i /archive", service_options)
        self.assertNotIn(
            "reqrep ^([^\\ ]*)\\ /archive/(.*) \\1\\ /\\2", service_options)
        self.assertNotIn(
            "use_backend landscape-pppa-proxy if pppa-proxy", service_options)

        backends = https_service["backends"]
        pppa_proxy_backends = [
            backend for backend in backends
            if backend["backend_name"] == "landscape-pppa-proxy"]
        self.assertEqual([], pppa_proxy_backends)

    def test_provide_data_with_pppa_proxy(self):
        """
        When HostedProvider specifies pppa-proxy configuration, entries
        for pppa-proxy backend and /archive frontend are introduced.
        """
        self.hookenv.leader = False
        hosted_data = [{
            "ppas-to-proxy": (
                "16.03=http://ppa.launchpad.net/landscape/16.03/ubuntu,"
                "16.06=http://ppa.launchpad.net/landscape/16.06/ubuntu"),
            "supported-releases": "16.06",
        }]
        hosted_requirer = {"hosted": hosted_data}
        relation = HAProxyProvider(
            self.config_requirer, hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = relation.provide_data()

        services = yaml.safe_load(data["services"])
        https_service = services[1]
        self.assertEqual(
            [
                "mode http",
                "timeout client 300000",
                "timeout server 300000",
                "balance leastconn",
                "option httpchk HEAD / HTTP/1.0",
                "http-request set-header X-Forwarded-Proto https",
                "acl message path_beg -i /message-system",
                "acl attachment path_beg -i /attachment",
                "acl api path_beg -i /api",
                "acl prometheus_metrics path_beg -i /metrics",
                "http-request deny if prometheus_metrics",
                "use_backend landscape-message if message",
                "use_backend landscape-message if attachment",
                "use_backend landscape-api if api",
                "acl pppa-proxy path_beg -i /archive",
                "reqrep ^([^\\ ]*)\\ /archive/(.*) \\1\\ /\\2",
                "use_backend landscape-pppa-proxy if pppa-proxy",
            ],
            https_service["service_options"])

        backends = https_service["backends"]
        pppa_proxy_backends = [
            backend for backend in backends
            if backend["backend_name"] == "landscape-pppa-proxy"]
        self.assertEqual(
            {"backend_name": "landscape-pppa-proxy",
             "servers": [
                 ["landscape-pppa-proxy-landscape-server-0",
                  "1.2.3.4", 9298, SERVER_OPTIONS]]},
            pppa_proxy_backends[0])

    def test_provide_data_with_pppa_proxy_with_root_url(self):
        """
        When HostedProvider specifies pppa-proxy configuration, and
        root url is defined for landscape server charm, pppa-proxy is
        configured to serve under https://archive.<root-hostname>/ instead of
        /archive relative path.
        """
        self.hookenv.leader = False
        self.config_requirer["config"]["root-url"] = "https://landscape.dev/"
        hosted_data = [{
            "ppas-to-proxy": (
                "16.03=http://ppa.launchpad.net/landscape/16.03/ubuntu,"
                "16.06=http://ppa.launchpad.net/landscape/16.06/ubuntu"),
            "supported-releases": "16.06",
        }]
        hosted_requirer = {"hosted": hosted_data}
        relation = HAProxyProvider(
            self.config_requirer, hosted_requirer, paths=self.paths,
            hookenv=self.hookenv)

        data = relation.provide_data()

        services = yaml.safe_load(data["services"])
        https_service = services[1]
        self.assertEqual(
            [
                "mode http",
                "timeout client 300000",
                "timeout server 300000",
                "balance leastconn",
                "option httpchk HEAD / HTTP/1.0",
                "http-request set-header X-Forwarded-Proto https",
                "acl message path_beg -i /message-system",
                "acl attachment path_beg -i /attachment",
                "acl api path_beg -i /api",
                "acl prometheus_metrics path_beg -i /metrics",
                "http-request deny if prometheus_metrics",
                "use_backend landscape-message if message",
                "use_backend landscape-message if attachment",
                "use_backend landscape-api if api",
                "acl pppa-proxy hdr(host) -i archive.landscape.dev",
                "use_backend landscape-pppa-proxy if pppa-proxy",
            ],
            https_service["service_options"])

        backends = https_service["backends"]
        pppa_proxy_backends = [
            backend for backend in backends
            if backend["backend_name"] == "landscape-pppa-proxy"]
        self.assertEqual(
            {"backend_name": "landscape-pppa-proxy",
             "servers": [
                 ["landscape-pppa-proxy-landscape-server-0",
                  "1.2.3.4", 9298, SERVER_OPTIONS]]},
            pppa_proxy_backends[0])


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
