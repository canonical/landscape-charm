import base64
import os
import shutil
import tempfile
import yaml

from lib.relations import haproxy
from lib.relations.haproxy import HAProxyProvider, SERVER_OPTIONS
from lib.tests.helpers import HookenvTest


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
        def faux_get_error_files():
            return [{"http_status": "500", "content": "blah"}]

        relation = HAProxyProvider()
        original_get_error_files = haproxy.get_error_files
        haproxy.get_error_files = faux_get_error_files

        data = relation.provide_data()
        # restore the monkey patched version
        haproxy.get_error_files = original_get_error_files

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
             "errorfiles": [{"http_status": "500", "content": "blah"}],
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
             "errorfiles": [{"http_status": "500", "content": "blah"}],
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


    def test_get_error_files(self):
        """
        The get_error_files function returns a list of dicts, with
        "http_status" and "content" keys.
        """
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir)

        error_file_names = ["unauthorized-haproxy.html",
                            "exception-haproxy.html",
                            "unplanned-offline-haproxy.html",
                            "timeout-haproxy.html"]

        fake_content = "Fake."
        fake_content_b64 = base64.b64encode(fake_content)

        for filename in error_file_names:
            with open(os.path.join(temp_dir, filename), "w") as thefile:
                thefile.write(fake_content)

        expected = [
                {"http_status": "403", "content": fake_content_b64},
                {"http_status": "500", "content": fake_content_b64},
                {"http_status": "502", "content": fake_content_b64},
                {"http_status": "503", "content": fake_content_b64},
                {"http_status": "504", "content": fake_content_b64},]

        result = haproxy.get_error_files(location=temp_dir)
        self.assertItemsEqual(expected, result)
