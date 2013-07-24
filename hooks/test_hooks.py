import hooks
import unittest
import yaml


class TestJuju(object):
    """
    Testing object to intercept juju calls and inject data, or make sure
    certain data is set.
    """
    _relation_data = {}
    def relation_set(self, *args, **kwargs):
        """
        Capture result of relation_set into _relation_data, which 
        can then be checked later.
        """
        self._relation_data = dict(self._relation_data, **kwargs)
        for arg in args:
            (key, value) = arg.split("=")
            self._relation_data[key] = value
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
        _format_service sends back data in a form haproxy expects.
        The "bar" service (overridden above) does not have any options in
        the definition dict..
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

    def test_format_service_with_option(self):
        """
        _format_service sets things up as haproxy expects
        when one option is specified.  The "foo" service (overridden above),
        has just a single option specified
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
        _format_service sets things up as haproxy expects
        when many options are specified, the "baz" service (overridden above),
        has multiple options specified in the dict.
        """
        result = hooks._format_service("baz", **hooks.SERVICE["baz"])
        baseline = {"service_name": "baz",
                    "servers": [["baz", "localhost", "82", "server"]],
                    "service_options": ["options"]}
        self.assertEqual(baseline, result)

    def test_get_services(self):
        """
        helper method get_services bulk-gets data in a format that haproxy
        expects.
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
