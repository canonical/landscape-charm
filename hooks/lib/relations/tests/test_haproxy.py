import tempfile
import yaml

from base64 import b64encode

from lib.relations.haproxy import (
    HAProxyProvider, SERVER_OPTIONS, ERRORFILES_MAP)
from lib.hook import HookError
from lib.tests.helpers import HookenvTest
from lib.tests.offline_fixture import OfflineDir


class HAProxyProviderTest(HookenvTest):

    with_hookenv_monkey_patch = True

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
        offline_dir = self.useFixture(OfflineDir()).path
        relation = HAProxyProvider(offline_dir=offline_dir)

        expected_errorfiles = []

        for error_code, filename in sorted(ERRORFILES_MAP.items()):
            expected_content = b64encode("Fake %s" % filename)
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
                      ["landscape-pingserver-landscape-server-0",
                       "1.2.3.4", 8070, SERVER_OPTIONS]]}]},
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
             "crts": ["DEFAULT"],
             "servers": [
                 ["landscape-appserver-landscape-server-0",
                  "1.2.3.4", 8080, SERVER_OPTIONS]],
             "backends": [
                 {"backend_name": "landscape-message",
                  "servers": [
                      ["landscape-message-server-landscape-server-0",
                       "1.2.3.4", 8090, SERVER_OPTIONS]]},
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
        offline_dir = tempfile.mkdtemp()  # Do not creat the files.
        provider = HAProxyProvider(offline_dir=offline_dir)

        self.assertRaises(HookError, provider.provide_data)
