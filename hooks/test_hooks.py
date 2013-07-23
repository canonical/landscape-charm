import hooks
import unittest
import yaml


class TestJuju(object):
    _relation_data = {}
    def relation_set(self, *args, **kwargs):
        self._relation_data = dict(self._relation_data, **kwargs)
        for i in args:
            (k, v) = i.split("=")
            self._relation_data[k] = v
        pass

    def unit_get(self, *args):
        return "localhost"

    def juju_log(self, *args, **kwargs):
        pass

    def config_get(self, scope=None):
        return {"services": "foo bar baz"}
        pass

    def relation_get(self, scope=None, unit_name=None, relation_id=None):
        pass


class TestHooks(unittest.TestCase):
    all_services = [
            {"service_name": "foo",
             "servers": [[
                 "foo", "localhost", "80",
                 "check inter 2000 rise 2 fall 5 maxconn 50"]],
             "service_options": [
                 "mode http", "balance leastconn", "option httpchk foo"]},
            {"service_name": "bar",
             "servers": [[
                 "bar", "localhost", "81",
                 "check inter 2000 rise 2 fall 5 maxconn 50"]],
             "service_options": [
                 "mode http", "balance leastconn",
                 "option httpchk GET / HTTP/1.0"]},
            {"service_name": "baz",
             "servers": [["baz", "localhost", "82", "server"]],
             "service_options": ["options"]}]
 
    def setUp(self):
        hooks.SERVICE = {"foo": {"port": "80", "httpchk": "foo"},
                         "bar": {"port": "81"},
                         "baz": {"port": "82", "httpchk": None,
                                 "server_options": "server",
                                 "service_options": ["options"]}}
        hooks.juju = TestJuju()

    def test_format_service(self):
        """
        Check that _format_service is sending back service data
        in a form haproxy expects
        """
        result = hooks._format_service("bar", **hooks.SERVICE["bar"])
        baseline = {"service_name": "bar",
                    "servers": [[
                        "bar", "localhost", "81",
                        "check inter 2000 rise 2 fall 5 maxconn 50"]],
                    "service_options": [
                        "mode http", "balance leastconn",
                        "option httpchk GET / HTTP/1.0"]}
        self.assertEqual(baseline, result)

    def test_format_service_with_options(self):
        """
        Check that _format_service sets things up as haproxy expects
        when one option is specified
        """
        result = hooks._format_service("foo", **hooks.SERVICE["foo"])
        baseline = {"service_name": "foo",
                    "servers": [[
                        "foo", "localhost", "80",
                        "check inter 2000 rise 2 fall 5 maxconn 50"]],
                    "service_options": [
                        "mode http", "balance leastconn", "option httpchk foo"]}
        self.assertEqual(baseline, result)

    def test_format_service_with_more_options(self):
        """
        Check that _format_service sets things up as haproxy expects
        when many options are specified
        """
        result = hooks._format_service("baz", **hooks.SERVICE["baz"])
        baseline = {"service_name": "baz",
                    "servers": [["baz", "localhost", "82", "server"]],
                    "service_options": ["options"]}
        self.assertEqual(baseline, result)

    def test_get_services(self):
        """
        Check the helper method get_services that bulk_gets data in a format
        that haproxy expects.
        """
        result = hooks._get_services()
        baseline = self.all_services
        self.assertEqual(baseline, result)

    def test_website_relation_joined(self):
        """
        Ensure the website relation joined hook spits out settings when run
        """
        hooks.website_relation_joined()
        baseline = {
            "services": yaml.safe_dump(self.all_services),
            "hostname": "localhost",
            "port": 80}
        self.assertEqual(baseline, hooks.juju._relation_data)

    def test_amqp_relation_joined(self):
        """
        Ensure the amqp relation joined hook spits out settings when run
        """
        hooks.amqp_relation_joined()
        baseline = {
            "username": "landscape",
            "vhost": "landscape"}
        self.assertEqual(baseline, hooks.juju._relation_data)
