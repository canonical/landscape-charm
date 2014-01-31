import hooks
import yaml
import os
import pycurl
import base64
import mocker
from ConfigParser import RawConfigParser


class TestJuju(object):
    """
    Testing object to intercept juju calls and inject data, or make sure
    certain data is set.
    """

    _outgoing_relation_data = ()   # set by local juju unit
    _incoming_relation_data = ()   # set by the REMOTE_JUJU_UNIT
    _logs = ()
    _relation_list = ("postgres/0",)

    def __init__(self):
        self.config = {
            "services": "msgserver pingserver juju-sync",
            "license-file": "LICENSE_FILE_TEXT",
            "service-count": "msgserver:2 pingserver:1",
            "upgrade-schema": False,
            "maintenance": False}

    def relation_set(self, *args, **kwargs):
        """
        Capture result of relation_set into _outgoing_relation_data, which
        can then be checked later.
        """
        if "relation_id" in kwargs:
            del kwargs["relation_id"]
        for key, value in kwargs.iteritems():
            self._outgoing_relation_data = (
                self._outgoing_relation_data + ((key, value),))
        for arg in args:
            (key, value) = arg.split("=")
            self._outgoing_relation_data = (
                self._outgoing_relation_data + ((key, value),))

    def relation_ids(self, relation_name="website"):
        """
        Hardcode expected relation_ids for tests.  Feel free to expand
        as more tests are added.
        """
        return ["%s:1" % relation_name]

    def relation_list(self, relation_id=None):
        """
        Hardcode expected relation_list for tests.  Feel free to expand
        as more tests are added.
        """
        return list(self._relation_list)

    def unit_get(self, *args):
        """
        for now the only thing this is called for is "public-address",
        so it's a simplistic return.
        """
        return "localhost"

    def local_unit(self):
        return hooks.os.environ["JUJU_UNIT_NAME"]

    def juju_log(self, message, level="INFO"):
        self._logs = self._logs + (message,)

    def config_get(self, scope=None):
        if scope is None:
            return self.config
        else:
            return self.config[scope]

    def relation_get(self, scope=None, unit_name=None, relation_id=None):
        if scope:
            for key, value in self._incoming_relation_data:
                if key == scope:
                    return value
            return None
        return dict(self._incoming_relation_data)


class TestHooks(mocker.MockerTestCase):

    def setUp(self):
        hooks._lsctl = lambda x: True
        hooks.juju = TestJuju()
        hooks.LANDSCAPE_LICENSE_DEST = self.makeFile()
        self._license_dest = open(hooks.LANDSCAPE_LICENSE_DEST, "w")
        hooks.LANDSCAPE_DEFAULT_FILE = self.makeFile()
        self._default_file = open(hooks.LANDSCAPE_DEFAULT_FILE, "w")
        hooks.LANDSCAPE_SERVICE_CONF = self.makeFile()
        self._service_conf = open(hooks.LANDSCAPE_SERVICE_CONF, "w")
        hooks.LANDSCAPE_NEW_SERVICE_CONF = self.makeFile()
        self._new_service_conf = open(hooks.LANDSCAPE_NEW_SERVICE_CONF, "w")
        hooks._get_system_numcpu = lambda: 2
        hooks._get_system_ram = lambda: 2
        self.maxDiff = None
        # Keep non-existent errorfiles from generating unrelated errors.
        for value in hooks.SERVICE_PROXY.values():
            if "errorfiles" in value.keys():
                value["errorfiles"] = []

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
        self.assertEqual(baseline, dict(hooks.juju._outgoing_relation_data))

    def test_amqp_relation_changed_no_hostname_password(self):
        """
        C{amqp-relation-changed} hook does not write C{LANDSCAPE_SERVICE_CONF}
        settings if the relation does not provide the required C{hostname} and
        C{password} relation data.
        """
        self.assertEqual((), hooks.juju._incoming_relation_data)
        self.assertRaises(SystemExit, hooks.amqp_relation_changed)
        message = (
            "Waiting for valid hostname/password values from amqp relation")
        self.assertIn(message, hooks.juju._logs)

    def test__download_file_success(self):
        """
        Make sure the happy path of download file works.
        """
        filename = self.makeFile()
        with open(filename, "w") as fp:
            fp.write("foobar")
        output = hooks._download_file("file://%s" % filename)
        self.assertIn("foobar", output)

    def test__download_file_failure(self):
        """The fail path of download file raises an exception."""
        self.assertRaises(
            pycurl.error, hooks._download_file, "file://FOO/NO/EXIST")

    def test__replace_in_file(self):
        """
        Test for replace_in_file to change some lines in a file, but not
        others.
        """
        filename = self.makeFile()
        with open(filename, "w") as fp:
            fp.write("foo\nfoo\nbar\nbaz\n")

        hooks._replace_in_file(filename, r"^f..$", "REPLACED")

        with open(filename, "r") as fp:
            content = fp.read()
        self.assertEqual("REPLACED\nREPLACED\nbar\nbaz\n", content)

    def test__enable_service(self):
        """Create a simple service enablement of a file with comments."""
        target = self.makeFile()
        with self._default_file as fp:
            fp.write("# Comment test\nRUN_APPSERVER=\"no\"\nRUN_CRON=\"yes\"")
        with open(target, "w") as fp:
            fp.write("# Comment test\nRUN_APPSERVER=3\nRUN_CRON=no")
        hooks.juju.config["services"] = "appserver"
        hooks._enable_services()
        self.assertFilesEqual(self._default_file.name, target)

    def test__enable_wrong_service(self):
        """Enable an unknown service, make sure exception is raised."""
        default = self.makeFile()
        with open(default, "w") as fp:
            fp.write("# Comment test\nRUN_APPSERVER=\"no\"")
        hooks.LANDSCAPE_DEFAULT_FILE = default
        hooks.juju.config["services"] = "INVALID_SERVICE_NAME"
        self.assertRaises(Exception, hooks._enable_services)

    def test__install_license_text(self):
        """Install a license with as a string."""
        hooks._install_license()
        self.assertFileContains(self._license_dest.name, "LICENSE_FILE_TEXT")

    def test__install_license_url(self):
        """Install a license with as a url."""
        source = self.makeFile()
        with open(source, "w") as fp:
            fp.write("LICENSE_FILE_TEXT from curl")
        hooks.juju.config["license-file"] = "file://%s" % source
        hooks._install_license()
        self.assertFileContains(
            self._license_dest.name, "LICENSE_FILE_TEXT from curl")

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
        service count of "AUTO" specified.  The number zero is specially
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
        data = dict(hooks.juju._outgoing_relation_data)
        self.assertNotEqual(len(data), 0)
        self.assertIn("services", data)
        for service in yaml.load(data["services"]):
            if service["service_name"] == "appserver":
                self.assertEqual(len(service["servers"]), 2)
                break
        else:
            assert False, "Didn't find element 'appserver'"

    def test_config_changed_starts_landscape(self):
        """
        config_changed() starts services when the database and amqp service are
        configured.
        """
        lsctl = self.mocker.replace(hooks._lsctl)
        lsctl("start")
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(True)
        is_amqp_up = self.mocker.replace(hooks._is_amqp_up)
        is_amqp_up()
        self.mocker.result(True)
        self.mocker.replay()

        hooks.config_changed()

    def test_config_changed_without_db_skips_start(self):
        """
        config_changed() does not start services when the database is not
        configured.
        """
        _lsctl = self.mocker.replace(hooks._lsctl)
        _lsctl("start")
        self.mocker.count(0, 0)
        _is_db_up = self.mocker.replace(hooks._is_db_up)
        _is_db_up()
        self.mocker.result(False)
        self.mocker.replay()

        hooks.config_changed()

    def test_config_changed_without_amqp_skips_start(self):
        """
        config_changed() does not start services when the amqp is not
        configured.
        """
        _lsctl = self.mocker.replace(hooks._lsctl)
        _lsctl("start")
        self.mocker.count(0, 0)
        _is_db_up = self.mocker.replace(hooks._is_db_up)
        _is_db_up()
        self.mocker.result(True)
        _is_amqp_up = self.mocker.replace(hooks._is_amqp_up)
        _is_amqp_up()
        self.mocker.result(False)
        self.mocker.replay()

        hooks.config_changed()

    def test_db_admin_relation_changed(self):
        """
        db_admin_relation_changed creates the database user and sets up
        landscape.
        """
        self.addCleanup(
            setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = {
            "host": "postgres/0", "user": "auto_db_admin",
            "password": "abc123",
            "allowed-units": "landscape/0 landscape/1",
            "state": "standalone"}.items()

        self.addCleanup(
            setattr, hooks.juju, "config_get", hooks.juju.config_get)
        hooks.juju.config_get = lambda x: "def456"

        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        parser.add_section("stores")
        parser.add_section("schema")
        parser.write(self._service_conf)
        self._service_conf.seek(0)

        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("postgres", "postgres/0", "auto_db_admin", "abc123")
        self.mocker.result(True)
        connect_exclusive = self.mocker.replace(hooks.util.connect_exclusive)
        connect_exclusive("postgres/0", "auto_db_admin", "abc123")
        connection = self.mocker.mock()
        self.mocker.result(connection)
        create_user = self.mocker.replace(hooks.util.create_user)
        create_user(connection, "landscape", "def456")
        check_call = self.mocker.replace(hooks.check_call)
        check_call("setup-landscape-server")
        connection.close()
        self.mocker.replay()

        hooks.db_admin_relation_changed()

    def test_db_admin_relation_changed_no_user(self):
        """
        db_admin_relation_changed does not configure landscape when the
        database is not yet configured.
        """
        self.addCleanup(
            setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = {
            "host": "postgres/0", "user": "", "password": "",
            "allowed-units": "landscape/0 landscape/1",
            "state": "standalone"}.items()

        self.addCleanup(
            setattr, hooks.juju, "config_get", hooks.juju.config_get)
        hooks.juju.config_get = lambda x: ""

        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        hooks.db_admin_relation_changed()

        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        self.assertEqual([], parser.sections())

    def test_db_admin_relation_changed_not_in_allowed_units(self):
        """
        db_admin_relation_changed does not configure landscape when the unit is
        not in allowed_units.  allowed_units is the postgres charm's official
        signal that database configuration can begin.
        """
        self.addCleanup(
            setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = {
            "host": "postgres/0", "user": "auto_db_admin",
            "password": "abc123", "allowed-units": "landscape/0",
            "state": "standalone"}.items()

        self.addCleanup(
            setattr, hooks.juju, "config_get", hooks.juju.config_get)
        hooks.juju.config_get = lambda x: ""

        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        hooks.db_admin_relation_changed()

        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        self.assertEqual([], parser.sections())

    def test_db_admin_relation_changed_hot_standby_state_ignore(self):
        """
        db_admin_relation_changed does not configure landscape when the unit
        is in a C{hot standby} state.
        """
        self.addCleanup(
            setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = {
            "host": "postgres/1", "user": "auto_db_admin",
            "password": "abc123", "allowed-units": "landscape/0",
            "state": "hot standby"}.items()

        self.addCleanup(
            setattr, hooks.juju, "config_get", hooks.juju.config_get)
        hooks.juju.config_get = lambda x: ""

        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/0"}  # allowed-units

        hooks.db_admin_relation_changed()

        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        self.assertEqual([], parser.sections())

    def test_db_admin_relation_changed_failover_state_ignore(self):
        """
        db_admin_relation_changed does not configure landscape when the unit
        is in a C{failover} state.
        """
        self.addCleanup(
            setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = {
            "host": "postgres/1", "user": "auto_db_admin",
            "password": "abc123", "allowed-units": "landscape/0",
            "state": "failover"}.items()

        self.addCleanup(
            setattr, hooks.juju, "config_get", hooks.juju.config_get)
        hooks.juju.config_get = lambda x: ""

        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/0"}  # allowed-units

        hooks.db_admin_relation_changed()

        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        self.assertEqual([], parser.sections())

    def test_db_admin_relation_changed_standalone_state_ignore(self):
        """
        When landscape is related to more than 1 postgres unit,
        C{db_admin_relation_changed} does not reconfigure landscape on
        receiving a C{standalone} state from additional new units. This
        occurs just after an add-unit postgresql is called as the
        new unit is installed, but that unit has not yet run any of its
        C{replication-relation-joined} hooks and is unaware of its clustering.
        """
        self.addCleanup(
            setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = {
            "host": "postgres/1", "user": "auto_db_admin",
            "password": "abc123", "allowed-units": "landscape/0",
            "state": "standalone"}.items()

        self.addCleanup(
            setattr, hooks.juju, "config_get", hooks.juju.config_get)
        hooks.juju.config_get = lambda x: ""

        self.addCleanup(
            setattr, hooks.juju, "_relation_list", ("postgres/0",))
        hooks.juju._relation_list = ("postgres/0", "postgres/1")

        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/0"}  # allowed-units

        hooks.db_admin_relation_changed()

        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        self.assertEqual([], parser.sections())

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

        hooks.juju.config["service-count"] = (
            "juju-sync:8 cron:0 appserver:AUTO")
        result = hooks._get_requested_service_count()
        self.assertEqual(result["juju-sync"], "8")
        self.assertEqual(result["cron"], "0")
        self.assertEqual(result["appserver"], "AUTO")
        self.assertEqual(result["pingserver"], "AUTO")

        hooks.juju.config["service-count"] = (
            "juju-sync:-8 cron:XYZ BLAh BLAh:X")
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
        hooks.juju.config["service-count"] = (
            "appserver:4 cron:10 pingserver:20")
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
        hooks.LANDSCAPE_MAINTENANCE = self.makeFile()
        hooks.juju.config["maintenance"] = True
        hooks._set_maintenance()
        self.assertTrue(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))
        hooks.juju.config["maintenance"] = False
        hooks._set_maintenance()
        self.assertFalse(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))

    def test_is_db_up_with_db_configured(self):
        """Return True when the db is configured."""
        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        parser.add_section("stores")
        parser.set("stores", "main", "somedb")
        parser.set("stores", "host", "somehost")
        parser.set("stores", "user", "someuser")
        parser.set("stores", "password", "somepassword")
        parser.write(self._service_conf)
        self._service_conf.seek(0)

        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("somedb", "somehost", "someuser", "somepassword")
        self.mocker.result(True)
        self.mocker.replay()

        self.assertTrue(hooks._is_db_up())

    def test_is_db_up_db_not_configured(self):
        """Return False when the db is not configured."""
        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        parser.add_section("stores")
        parser.set("stores", "main", "somedb")
        parser.set("stores", "host", "somehost")
        parser.set("stores", "user", "someuser")
        parser.set("stores", "password", "somepassword")
        parser.write(self._service_conf)
        self._service_conf.seek(0)

        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("somedb", "somehost", "someuser", "somepassword")
        self.mocker.result(False)
        self.mocker.replay()

        self.assertFalse(hooks._is_db_up())

    def test_is_db_up_no_service_config(self):
        """Return False when the service config does not exist."""
        hooks.LANDSCAPE_SERVICE_CONF = "/does/not/exist"
        self.assertFalse(hooks._is_db_up())

    def test_is_db_up_service_config_missing_stores(self):
        """Return False when the service config is missing [stores]."""
        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        parser.write(self._service_conf)
        self._service_conf.seek(0)
        self.assertFalse(hooks._is_db_up())

    def test_is_db_up_service_config_missing_keys(self):
        """Return False when the [stores] section is missing db settings."""
        parser = RawConfigParser()
        parser.read([hooks.LANDSCAPE_SERVICE_CONF])
        parser.add_section("stores")
        parser.write(self._service_conf)
        self._service_conf.seek(0)
        self.assertFalse(hooks._is_db_up())


class TestHooksServiceMock(TestHooks):

    all_services = [
        {"service_name": "foo",
         "servers": [[
             "foo", "localhost", "80",
             "check inter 5000 rise 2 fall 5 maxconn 50"]],
         "service_options": [
             "mode http", "balance leastconn", "option httpchk foo"],
         "errorfiles": []},
        {"service_name": "bar",
         "servers":
            [["bar", "localhost", "81",
              "check inter 5000 rise 2 fall 5 maxconn 50"],
             ["bar", "localhost", "82",
              "check inter 5000 rise 2 fall 5 maxconn 50"]],
         "service_options": [
             "mode http", "balance leastconn",
             "option httpchk GET / HTTP/1.0"],
         "errorfiles": []},
        {"service_name": "baz",
         "servers": [["baz", "localhost", "82", "server"],
                     ["baz", "localhost", "83", "server"],
                     ["baz", "localhost", "84", "server"]],
         "service_options": ["options"],
         "errorfiles": []}]

    def setUp(self):
        super(TestHooksServiceMock, self).setUp()
        self.filename = self.makeFile()
        file(self.filename, "w").write("<html></html>")
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
                "service_options": ["options"]},
            "qux": {
                "port": "83",
                "errorfiles": [{
                    "http_status": 403,
                    "path": self.filename}]}}
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
                        "check inter 5000 rise 2 fall 5 maxconn 50"]],
                    "service_options": [
                        "mode http", "balance leastconn",
                        "option httpchk GET / HTTP/1.0"],
                    "errorfiles": []}
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
                "check inter 5000 rise 2 fall 5 maxconn 50"]],
            "service_options": [
                "mode http", "balance leastconn", "option httpchk foo"],
            "errorfiles": []}
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
                    "service_options": ["options"],
                    "errorfiles": []}
        self.assertEqual(baseline, result)

    def test_format_service_with_errorfiles(self):
        """
        When errorfiles are specified, communicate them to the relation and
        include the file contents, base64 encoded.  Each errorfile spec
        includes the http code, the path and the file contents.
        """
        result = hooks._format_service("qux", 1, **hooks.SERVICE_PROXY["qux"])
        baseline = {
            "service_name": "qux",
            "servers": [["qux", "localhost", "83",
                         "check inter 5000 rise 2 fall 5 maxconn 50"]],
            "errorfiles": [{
                "http_status": 403,
                "path": self.filename,
                "content": base64.b64encode("<html></html>")}],
            "service_options": [
                "mode http", "balance leastconn",
                "option httpchk GET / HTTP/1.0"]}
        self.assertEqual(baseline, result)

    def test_format_service_with_errorfile_not_found(self):
        """
        A missing errorfile raises an IOError.
        """
        errorfiles = hooks.SERVICE_PROXY["qux"]["errorfiles"]
        errorfiles[0]["path"] = "/does/not/exist.html"
        self.assertRaises(IOError, hooks._format_service, "qux", 1,
                          **hooks.SERVICE_PROXY["qux"])

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
        baseline = (
            ("services", yaml.safe_dump(self.all_services)),
            ("hostname", "localhost"),
            ("port", 80))
        self.assertEqual(baseline, hooks.juju._outgoing_relation_data)

    def test_notify_website_relation(self):
        """
        notify_website_relation actually does a relation set with
        my correct mocked data.
        """
        hooks.notify_website_relation()
        baseline = (("services", yaml.safe_dump(self.all_services)),)
        self.assertEqual(baseline, hooks.juju._outgoing_relation_data)
