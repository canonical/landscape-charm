import yaml
from base64 import b64encode

from lib.relations.haproxy import (HAProxyProvider, SERVER_OPTIONS,
    ERRORFILES_MAP)
from lib.tests.helpers import HookenvTest, ErrorFilesTestMixin


class HAProxyProviderTest(HookenvTest, ErrorFilesTestMixin):

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
        offline_dir = self.setup_error_files(ERRORFILES_MAP)
        relation = HAProxyProvider(offline_folder=offline_dir)

        expected_errorfiles = []

        for error_code, filename in ERRORFILES_MAP.items():
            expected_content = b64encode("Fake %s" % filename)
            expected_errorfiles.append(
                {"http_status": error_code, "content": expected_content})

#        expected_errorfiles = [
#                {"http_status": "503", "content": self.fake_content_b64},
                # TODO: Uncomment the following lines once #1437366 is fixed.
                #{"http_status": "403", "content": fake_content_b64},
                #{"http_status": "500", "content": fake_content_b64},
                #{"http_status": "502", "content": fake_content_b64},
                #{"http_status": "503", "content": fake_content_b64},
                #{"http_status": "504", "content": fake_content_b64},
#                ]

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
