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
        self.config = {
            "services": "msgserver pingserver juju-sync",
            "license-file": "LICENSE_FILE_TEXT",
            "service-count": "msgserver:2 pingserver:1",
            "upgrade-schema": False,
            "maintenance": False}

    def relation_set(self, *args, **kwargs):
        """
        Capture result of relation_set into _relation_data, which
        can then be checked later.
        """
        if "relation_id" in kwargs:
            del kwargs["relation_id"]
        self._relation_data = dict(self._relation_data, **kwargs)
        for arg in args:
            (key, value) = arg.split("=")
            self._relation_data[key] = value
        pass

    def relation_ids(self, relation_name="website"):
        """
        Hardcode expected relation_ids for tests.  Feel free to expand
        as more tests are added.
        """
        return ["%s:1" % relation_name]

    def unit_get(self, *args):
        """
        for now the only thing this is called for is "public-address",
        so it's a simplistic return.
        """
        return "localhost"

    def juju_log(self, *args, **kwargs):
        pass

    def config_get(self, scope=None):
        if scope is None:
            return self.config
        else:
            return self.config[scope]

    def relation_get(self, scope=None, unit_name=None, relation_id=None):
        pass


class TestHooks(unittest.TestCase):

    def setUp(self):
        hooks._lsctl = lambda x: True
        hooks.juju = TestJuju()
        self._license_dest = tempfile.NamedTemporaryFile(delete=False)
        hooks.LANDSCAPE_LICENSE_DEST = self._license_dest.name
        self._default_file = tempfile.NamedTemporaryFile(delete=False)
        hooks.LANDSCAPE_DEFAULT_FILE = self._default_file.name
        hooks._get_system_numcpu = lambda: 2
        hooks._get_system_ram = lambda: 2
        self.maxDiff = None

    def assertFileContains(self, filename, text):
        """Make sure a string exists in a file."""
        with open(filename, "r") as fp:
            contents = fp.read()
        self.assertIn(text, contents)

    def assertFilesEqual(self, file1, file2):
        """Given two filenames, compare them."""
        with open(file1, "r") as fp1:
            contents1 = fp1.read()
        with open(file2, "r") as fp2:
            contents2 = fp2.read()
        self.assertEqual(contents1, contents2)

    def seed_default_file_services_off(self):
        with self._default_file as fp:
            fp.write("""
# Comment test
RUN_APPSERVER="no"
RUN_MSGSERVER="no"
RUN_JUJU_SYNC="no"
RUN_PINGSERVER="yes"
UPGRADE_SCHEMA="no"
            """)


class TestHooksService(TestHooks):

    def test_get_services_non_proxied(self):
        """
        helper method should not break if non-proxied services are called for
        (e.g.: jobhandler).
        """
        hooks.juju.config["services"] = "jobhandler"
        result = hooks._get_services_haproxy()
        self.assertEqual(len(result), 0)

    def test_amqp_relation_joined(self):
        """
        Ensure the amqp relation joined hook spits out settings when run.
        """
        hooks.amqp_relation_joined()
        baseline = {
            "username": "landscape",
            "vhost": "landscape"}
        self.assertEqual(baseline, hooks.juju._relation_data)

    def test__download_file_success(self):
        """
        Make sure the happy path of download file works.
        """
        tmp = tempfile.NamedTemporaryFile(delete=False)
        with tmp as fp:
            fp.write("foobar")
        output = hooks._download_file("file://%s" % tmp.name)
        os.unlink(tmp.name)
        self.assertTrue("foobar" in output)

    def test__download_file_failure(self):
        """The fail path of download file raises an exception."""
        self.assertRaises(
            pycurl.error, hooks._download_file, "file://FOO/NO/EXIST")

    def test__replace_in_file(self):
        """
        Test for replace_in_file to change some lines in a file, but not
        others.
        """
        tmp = tempfile.NamedTemporaryFile(delete=False)
        with tmp as fp:
            fp.write("foo\nfoo\nbar\nbaz\n")

        hooks._replace_in_file(tmp.name, r"^f..$", "REPLACED")

        with open(tmp.name, "r") as fp:
            content = fp.read()
        os.unlink(tmp.name)
        self.assertEquals("REPLACED\nREPLACED\nbar\nbaz\n", content)

    def test__enable_service(self):
        """Create a simple service enablement of a file with comments."""
        target = tempfile.NamedTemporaryFile(delete=False)
        with self._default_file as fp:
            fp.write("# Comment test\nRUN_APPSERVER=\"no\"\nRUN_CRON=\"yes\"")
        with target as fp:
            fp.write("# Comment test\nRUN_APPSERVER=3\nRUN_CRON=no")
        hooks.juju.config["services"] = "appserver"
        hooks._enable_services()
        self.assertFilesEqual(self._default_file.name, target.name)
        os.unlink(target.name)
        pass

    def test__enable_wrong_service(self):
        """Enable an unknown service, make sure exception is raised."""
        default = tempfile.NamedTemporaryFile(delete=False)
        with default as fp:
            fp.write("# Comment test\nRUN_APPSERVER=\"no\"")
        hooks.LANDSCAPE_DEFAULT_FILE = default.name
        hooks.juju.config["services"] = "INVALID_SERVICE_NAME"
        self.assertRaises(Exception, hooks._enable_services)
        os.unlink(default.name)
        pass

    def test__install_license_text(self):
        """Install a license with as a string."""
        hooks._install_license()
        self.assertFileContains(self._license_dest.name, "LICENSE_FILE_TEXT")

    def test__install_license_url(self):
        """Install a license with as a url."""
        source = tempfile.NamedTemporaryFile(delete=False)
        with source as fp:
            fp.write("LICENSE_FILE_TEXT from curl")
        hooks.juju.config["license-file"] = "file://%s" % source.name
        hooks._install_license()
        self.assertFileContains(
            self._license_dest.name, "LICENSE_FILE_TEXT from curl")
        os.unlink(source.name)

    def test_config_changed(self):
        """
        All defaults should apply to requested services with the default
        service count of "AUTO" specified.
        """
        hooks.juju.config["services"] = "appserver msgserver juju-sync"
        hooks.juju.config["service-count"] = "AUTO"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=yes")
        self.assertFileContains(self._default_file.name, "\nRUN_PINGSERVER=no")

    def test_config_changed_zero(self):
        """
        All defaults should apply to requested services with the default
        service count of "AUTO" specified, the number zero is specially
        recognized in the code (negative numbers and other junk will not
        match the regular expression of integer).
        """
        hooks.juju.config["services"] = "appserver msgserver juju-sync"
        hooks.juju.config["service-count"] = "0"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=yes")
        self.assertFileContains(self._default_file.name, "\nRUN_PINGSERVER=no")

    def test_config_changed_service_count_bare(self):
        """
        Bare number (integer) sets all capable services to that number, ones
        with lower maximums ignore it.
        """
        hooks.juju.config["services"] = "appserver msgserver juju-sync"
        hooks.juju.config["service-count"] = "2"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=2")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=2")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=yes")
        self.assertFileContains(self._default_file.name, "\nRUN_PINGSERVER=no")

    def test_config_changed_service_count_labeled(self):
        """
        Multiple labeled service counts resolve correctly, missing service
        default to auto-determined, the keyword AUTO should also be recognized.
        """
        hooks.juju.config["services"] = "appserver msgserver juju-sync"
        hooks.juju.config["service-count"] = "appserver:AUTO juju-sync:10"
        self.seed_default_file_services_off()
        hooks.config_changed()
        self.assertFileContains(self._default_file.name, "\nRUN_APPSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_MSGSERVER=3")
        self.assertFileContains(self._default_file.name, "\nRUN_JUJU_SYNC=yes")
        self.assertFileContains(self._default_file.name, "\nRUN_PINGSERVER=no")

    def test_config_changed_service_count_update_haproxy(self):
        """
        run the config_changed hook, we should emit a relation_changed
        to haproxy giving 2 servers in the appserver service entry.
        """
        hooks.juju.config["services"] = "appserver msgserver juju-sync"
        hooks.juju.config["service-count"] = "2"
        self.seed_default_file_services_off()
        hooks.config_changed()
        data = hooks.juju._relation_data
        self.assertNotEqual(len(data), 0)
        self.assertIn("services", data)
        for service in yaml.load(data["services"]):
            if service["service_name"] == "appserver":
                self.assertEquals(len(service["servers"]), 2)
                break
        else:
            assert False, "Didn't find element 'appserver'"

    def test_calc_daemon_count(self):
        """
        Test various interesting inputs of _calc_daemon_count.
        """
        calc = hooks._calc_daemon_count
        # min/max = autogen limits, req = requested value, max2 = hard limit
        #                       |min max max2  req|
        #                       |---|---|----|----|
        self.assertEqual(calc("x", 1, 4,   9, "4"), 4)
        self.assertEqual(calc("x", 1, 3, None, "2"), 2)
        self.assertEqual(calc("x", 1, 9,   9, "AUTO"), 3)
        self.assertEqual(calc("x", 4, 9,   9, None), 4)
        self.assertEqual(calc("x", 4, 9,   9, "1"), 1)
        self.assertEqual(calc("x", 4, 9,   9, "10"), 9)
        self.assertEqual(calc("x", 4, 9,   8, "10"), 8)
        # 0 requested is not valid, maps to AUTO
        self.assertEqual(calc("x", 0, 4, None, "0"), 3)

    def test_get_requested_service_count(self):
        """
        service-count setting can look as follows:
          - 2
          - appserver:2 pingserver:2
          - appserver:AUTO
          - AUTO

        Things not understood should fallback to AUTO.  This method
        returns a dict with each known service as the key and the
        parsed requested count as a value.  If a count wasn't requested
        explicitly, it defaults to AUTO.  0 is parsed as is, but later
        on is explicitly mapped to AUTO.

        Also, the length of the dict is checked to make sure it
        contains all known services.
        """
        hooks.juju.config["service-count"] = "0"
        result = hooks._get_requested_service_count()
        self.assertEqual(len(result), 12)
        self.assertEqual(result["appserver"], "0")

        hooks.juju.config["service-count"] = "foo"
        result = hooks._get_requested_service_count()
        self.assertEqual(result["msgserver"], "AUTO")

        hooks.juju.config["service-count"] = "AUTO"
        result = hooks._get_requested_service_count()
        self.assertEqual(result["pingserver"], "AUTO")

        hooks.juju.config["service-count"] = "8"
        result = hooks._get_requested_service_count()
        self.assertEqual(result["juju-sync"], "8")

        hooks.juju.config["service-count"] = "juju-sync:8 cron:0 appserver:AUTO"
        result = hooks._get_requested_service_count()
        self.assertEqual(result["juju-sync"], "8")
        self.assertEqual(result["cron"], "0")
        self.assertEqual(result["appserver"], "AUTO")
        self.assertEqual(result["pingserver"], "AUTO")

        hooks.juju.config["service-count"] = "juju-sync:-8 cron:XYZ BLAh BLAh:X"
        result = hooks._get_requested_service_count()
        self.assertEqual(len(result), 12)
        self.assertEqual(result["juju-sync"], "AUTO")
        self.assertEqual(result["cron"], "AUTO")
        self.assertEqual(result["appserver"], "AUTO")
        self.assertNotIn("BLAh", result)

    def test_get_services_dict(self):
        """
        The services dict contains service names as keys
        and daemon counts (int) as values.  These counts are not requested
        but are the actual number we plan to launch. Make sure it's valid for
        a couple combinations of "services" and "service_count".
        """
        hooks.juju.config["services"] = "appserver"
        hooks.juju.config["service-count"] = "2"
        result = hooks._get_services_dict()
        self.assertEqual(result, {"appserver": 2})

        hooks.juju.config["services"] = "appserver pingserver cron"
        hooks.juju.config["service-count"] = "appserver:4 cron:10 pingserver:20"
        result = hooks._get_services_dict()
        self.assertEqual(result, {"appserver": 4, "cron": 1, "pingserver": 9})

        hooks.juju.config["services"] = "appserver cron"
        hooks.juju.config["service-count"] = "AUTO"
        result = hooks._get_services_dict()
        self.assertEqual(result, {"appserver": 3, "cron": 1})

    def test_get_requested_services(self):
        """
        "services" config is parsed into list.  Exceptions are raised for
        invalid requests since the user probably would not catch it otherwise.
        """
        hooks.juju.config["services"] = "appserver"
        result = hooks._get_requested_services()
        self.assertEqual(["appserver"], result)

        hooks.juju.config["services"] = "appserver pingserver cron"
        result = hooks._get_requested_services()
        self.assertEqual(["appserver", "pingserver", "cron"], result)

        hooks.juju.config["services"] = "appserver pingserver cron foo"
        self.assertRaises(Exception, hooks._get_requested_services)

    def test_upgrade_schema(self):
        """Test both the false and true case of upgrade schema."""
        self.seed_default_file_services_off()
        hooks.juju.config["upgrade-schema"] = True
        hooks._set_upgrade_schema()
        self.assertFileContains(self._default_file.name, "UPGRADE_SCHEMA=yes")
        hooks.juju.config["upgrade-schema"] = False
        hooks._set_upgrade_schema()
        self.assertFileContains(self._default_file.name, "UPGRADE_SCHEMA=no")

    def test_maintenance(self):
        """When maintenance is set, a file is created on the filesystem."""
        filename = tempfile.NamedTemporaryFile(delete=False).name
        os.unlink(filename)
        hooks.LANDSCAPE_MAINTENANCE = filename
        hooks.juju.config["maintenance"] = True
        hooks._set_maintenance()
        self.assertTrue(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))
        hooks.juju.config["maintenance"] = False
        hooks._set_maintenance()
        self.assertFalse(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))


class TestHooksServiceMock(TestHooks):
    all_services = [
            {"service_name": "foo",
             "servers": [[
                 "foo", "localhost", "80",
                 "check inter 2000 rise 2 fall 5 maxconn 50"]],
             "service_options": [
                 "mode http", "balance leastconn", "option httpchk foo"]},
            {"service_name": "bar",
             "servers":
                [["bar", "localhost", "81",
                 "check inter 2000 rise 2 fall 5 maxconn 50"],
                 ["bar", "localhost", "82",
                 "check inter 2000 rise 2 fall 5 maxconn 50"]],
             "service_options": [
                 "mode http", "balance leastconn",
                 "option httpchk GET / HTTP/1.0"]},
            {"service_name": "baz",
             "servers": [["baz", "localhost", "82", "server"],
                         ["baz", "localhost", "83", "server"],
                         ["baz", "localhost", "84", "server"]],
             "service_options": ["options"]}]

    def setUp(self):
        super(TestHooksServiceMock, self).setUp()
        self.mock_service_data()

    def tearDown(self):
        self.restore_service_data()
        super(TestHooksServiceMock, self).tearDown()

    def restore_service_data(self):
        hooks.juju.config = self.config
        hooks.SERVICE_PROXY = self._SERVICE_PROXY
        hooks.SERVICE_DEFAULT = self._SERVICE_DEFAULT
        hooks.SERVICE_COUNT = self._SERVICE_COUNT

    def mock_service_data(self):
        self.config = hooks.juju.config
        self._SERVICE_PROXY = hooks.SERVICE_PROXY
        self._SERVICE_DEFAULT = hooks.SERVICE_DEFAULT
        self._SERVICE_COUNT = hooks.SERVICE_COUNT

        hooks.juju.config["services"] = "foo bar baz"
        hooks.juju.config["service-count"] = "foo:1 bar:2"
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
        hooks.SERVICE_COUNT = {
            "foo": [1, 4, None],
            "bar": [1, 4, None],
            "baz": [1, 4, None]}

    def test_format_service(self):
        """
        _format_service sends back data in a form haproxy expects.
        The "bar" service (overridden above) does not have any options in
        the definition dict.
        """
        result = hooks._format_service("bar", 1, **hooks.SERVICE_PROXY["bar"])
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
        has just a single option specified.
        """
        result = hooks._format_service("foo", 1, **hooks.SERVICE_PROXY["foo"])
        baseline = {
                "service_name": "foo",
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
        has multiple options specified in the dict.  Also, specify a higher
        server count and make sure servers reacts accordingly.
        """
        result = hooks._format_service("baz", 2, **hooks.SERVICE_PROXY["baz"])
        baseline = {"service_name": "baz",
                    "servers": [["baz", "localhost", "82", "server"],
                                ["baz", "localhost", "83", "server"]],
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
        Ensure the website relation joined hook spits out settings when run.
        """
        hooks.website_relation_joined()
        baseline = {
            "services": yaml.safe_dump(self.all_services),
            "hostname": "localhost",
            "port": 80}
        self.assertEqual(baseline, hooks.juju._relation_data)

    def test_notify_website_relation(self):
        """
        notify_website_relation actually does a relation set with
        my correct mocked data.
        """
        hooks.notify_website_relation()
        baseline = {
            "services": yaml.safe_dump(self.all_services)}
        self.assertEqual(baseline, hooks.juju._relation_data)
