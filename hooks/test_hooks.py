import hooks
import unittest
import yaml
import tempfile
import os
import pycurl

class TestJuju(object):
    """
    Testing object to intercept juju calls and inject data, or make sure
    certain data is set.
    """
    _relation_data = {}
    def __init__(self):
        self._test_license_file = "LICENSE_FILE_TEXT"
        self._test_services = "msgserver pingserver juju-sync"
        self._test_service_count = "msgserver:2 pingserver:1"

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
        if scope is None:
            return {"services": self._test_services}
        elif scope == "license-file":
            return self._test_license_file
        elif scope == "service-count":
            return self._test_service_count
        pass

    def relation_get(self, scope=None, unit_name=None, relation_id=None):
        pass

class TestHooks(unittest.TestCase):

    def setUp(self):
        hooks._lsctl_restart = lambda: True
        hooks.juju = TestJuju()
        self._license_dest = tempfile.NamedTemporaryFile(delete=False)
        hooks.LANDSCAPE_LICENSE_DEST = self._license_dest.name
        self._default_file = tempfile.NamedTemporaryFile(delete=False)
        hooks.LANDSCAPE_DEFAULT_FILE = self._default_file.name
        hooks._get_system_numcpu = lambda: 2
        hooks._get_system_ram = lambda: 2

    def assertFileContains(self, filename, text):
        """ Make sure a string exists in a file """
        with open(filename, 'r') as fp:
            contents = fp.read()
        self.assertIn(text, contents)

    def assertFilesEqual(self, file1, file2):
        """ Given two filenames, compare them """
        with open(file1, 'r') as fp1:
            contents1 = fp1.read()
        with open(file2, 'r') as fp2:
            contents2 = fp2.read()
        self.assertEqual(contents1, contents2)

    def seed_default_file_services_off(self):
        with self._default_file as fp:
            fp.write('# Comment test\nRUN_APPSERVER="no"\nRUN_MSGSERVER="no"\nRUN_JUJU_SYNC="no"')
            fp.flush()

class TestHooksService(TestHooks):

    def setUp(self):
        super(TestHooksService, self).setUp()

    def tearDown(self):
        super(TestHooksService, self).tearDown()

    def test_get_services_non_proxied(self):
        """
        helper method should not break if non-proxied services are called for
        (e.g.: jobhandler)
        """
        #hooks.juju._test_services = "jobhandler"
        #hooks._get_services_haproxy()
        pass

    def test_amqp_relation_joined(self):
        """
        Ensure the amqp relation joined hook spits out settings when run
        """
        hooks.amqp_relation_joined()
        baseline = {
            "username": "landscape",
            "vhost": "landscape"}
        self.assertEqual(baseline, hooks.juju._relation_data)

    def test__download_file_success(self):
        """
        Make sure the happy path of download file works
        """
        tmp = tempfile.NamedTemporaryFile(delete=False)
        with tmp as fp:
            fp.write("foobar")
            fp.flush()
        output = hooks._download_file("file://%s" % tmp.name)
        os.unlink(tmp.name)
        self.assertTrue("foobar" in output)

    def test__download_file_failure(self):
        """ The fail path of download file raises an exception """
        self.assertRaises(pycurl.error, hooks._download_file, "file://FOO/NO/EXIST")

    def test__replace_in_file(self):
        """
        Test for replace_in_file to change some lines in a file, but not
        others
        """
        tmp = tempfile.NamedTemporaryFile(delete=False)
        with tmp as fp:
            fp.write("foo\nfoo\nbar\nbaz\n")
            fp.flush()

        hooks._replace_in_file(tmp.name, r'^f..$', "REPLACED")

        with open(tmp.name, 'r') as fp:
            content = fp.read()
        os.unlink(tmp.name)
        self.assertEquals("REPLACED\nREPLACED\nbar\nbaz\n", content)

    def test__enable_service(self):
        """ Create a simple service enablement of a file with comments """
        target = tempfile.NamedTemporaryFile(delete=False)
        with self._default_file as fp:
            fp.write('# Comment test\nRUN_APPSERVER="no"')
            fp.flush()
        with target as fp:
            fp.write('# Comment test\nRUN_APPSERVER=3')
            fp.flush()
        hooks.juju._test_services = "appserver"
        hooks._enable_services()
        self.assertFilesEqual(self._default_file.name, target.name)
        os.unlink(target.name)
        pass

    def test__enable_wrong_service(self):
        """ Create a simple service enablement of a file with comments """
        default = tempfile.NamedTemporaryFile(delete=False)
        with default as fp:
            fp.write('# Comment test\nRUN_APPSERVER="no"')
            fp.flush()
        hooks.LANDSCAPE_DEFAULT_FILE = default.name
        hooks.juju._test_services = "INVALID_SERVICE_NAME"
        self.assertRaises(Exception, hooks._enable_services)
        os.unlink(default.name)
        pass

    def test__install_license_text(self):
        """ Install a license with as a string """
        hooks._install_license()
        self.assertFileContains(self._license_dest.name, "LICENSE_FILE_TEXT")

    def test__install_license_url(self):
        """ Install a license with as a url """
        source = tempfile.NamedTemporaryFile(delete=False)
        with source as fp:
            fp.write("LICENSE_FILE_TEXT from curl")
            fp.flush()
        hooks.juju._test_license_file = "file://%s" % source.name
        hooks._install_license()
        self.assertFileContains(
            self._license_dest.name, "LICENSE_FILE_TEXT from curl")
        os.unlink(source.name)

    def test_config_changed(self):
        """
        All defaults should apply to requested services with the default
        service count of "AUTO" specified
        """
        hooks.juju._test_services = "appserver msgserver juju-sync"
        hooks.juju._test_service_count = "AUTO"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=1")

    def test_config_changed_zero(self):
        """
        All defaults should apply to requested services with the default
        service count of "AUTO" specified, the number zero is specially
        recognized in the code (negative numbers and other junk will not
        match the regular expression of integer)
        """
        hooks.juju._test_services = "appserver msgserver juju-sync"
        hooks.juju._test_service_count = "0"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=1")

    def test_config_changed_service_count_bare(self):
        """
        Bare number (integer) sets all capable services to that number, ones with
        lower maximums ignore it.
        """
        hooks.juju._test_services = "appserver msgserver juju-sync"
        hooks.juju._test_service_count = "2"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=2")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=2")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=1")

    def test_config_changed_service_count_labeled(self):
        """
        Multiple labeled service counts resolve correctly, missing service
        default to auto-determined, the keyword AUTO should also be recognized
        """
        hooks.juju._test_services = "appserver msgserver juju-sync"
        hooks.juju._test_service_count = "appserver:AUTO juju-sync:10"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=1")

    def test_config_changed_service_count_update_haproxy(self):
        """
        Bare number (integer) sets all capable services to that number, ones with
        lower maximums ignore it.
        """
        hooks.juju._test_services = "appserver msgserver juju-sync"
        hooks.juju._test_service_count = "2"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertTrue(len(hooks.juju._relation_data) > 0)

class TestHooksServiceMock(TestHooks):
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
        super(TestHooksServiceMock, self).setUp()
        self.mock_service_data()

    def tearDown(self):
        self.restore_service_data()
        super(TestHooksServiceMock, self).tearDown()

    def restore_service_data(self):
        hooks.juju._test_services = self._test_services
        hooks.juju._test_service_count = self._test_service_count
        hooks.SERVICE_PROXY = self._SERVICE_PROXY
        hooks.SERVICE_DEFAULT = self._SERVICE_DEFAULT

    def mock_service_data(self):
        self._test_services = hooks.juju._test_services
        self._test_service_count = hooks.juju._test_service_count
        self._SERVICE_PROXY = hooks.SERVICE_PROXY
        self._SERVICE_DEFAULT = hooks.SERVICE_DEFAULT

        hooks.juju._test_services = "foo bar baz"
        hooks.juju._test_service_count = "foo:1 bar:2"
        hooks.SERVICE_PROXY = {
            "foo": {"port": "80", "httpchk": "foo"},
            "bar": {"port": "81"},
            "baz": {
                "port": "82", "httpchk": None,
                "server_options": "server",
                "service_options": ["options"]}}
        hooks.SERVICE_DEFAULT = {
            "foo": "FOO",
            "bar": "BAR",
            "baz": "BAZ"}

    def test_format_service(self):
        """
        _format_service sends back data in a form haproxy expects.
        The "bar" service (overridden above) does not have any options in
        the definition dict..
        """
        result = hooks._format_service("bar", **hooks.SERVICE_PROXY["bar"])
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
        result = hooks._format_service("foo", **hooks.SERVICE_PROXY["foo"])
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
        result = hooks._format_service("baz", **hooks.SERVICE_PROXY["baz"])
        baseline = {"service_name": "baz",
                    "servers": [["baz", "localhost", "82", "server"]],
                    "service_options": ["options"]}
        self.assertEqual(baseline, result)

    def test_get_services(self):
        """
        helper method get_services bulk-gets data in a format that haproxy
        expects.
        """
        result = hooks._get_services_haproxy()
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

