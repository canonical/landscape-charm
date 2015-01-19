from configobj import ConfigObj
import base64
import hooks
import mocker
import os
import psycopg2
import pycurl
import stat
import subprocess
import tempfile
import unittest
import yaml


class CurlStub(object):

    urls = []

    def __init__(self, result=None, infos=None, error=None):
        pass

    def setopt(self, option, value):
        if option == pycurl.URL:
            if "\n" in value or "\r" in value:
                raise AssertionError("URL cannot contain linefeed or newline")
            self.urls.append(value)

    def perform(self):
        pass

    def close(self):
        pass


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
            "maintenance": False,
            "admin-name": None,
            "admin-email": None,
            "admin-password": None}

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
        if relation_id == "website:1":
            return ["landscape-haproxy/0"]
        else:
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
        hooks.util.juju = hooks.juju
        hooks.LANDSCAPE_LICENSE_DEST = self.makeFile()
        hooks.LANDSCAPE_DEFAULT_FILE = self.makeFile()
        self._default_file = open(hooks.LANDSCAPE_DEFAULT_FILE, "w")
        hooks.LANDSCAPE_SERVICE_CONF = self.makeFile()
        self._service_conf = open(hooks.LANDSCAPE_SERVICE_CONF, "w")
        hooks._get_system_numcpu = lambda: 2
        hooks._get_system_ram = lambda: 2
        self.maxDiff = None
        # Keep non-existent errorfiles from generating unrelated errors.
        for value in hooks.SERVICE_PROXY.values():
            if "errorfiles" in value.keys():
                value["errorfiles"] = []

    def tearDown(self):
        if "JUJU_RELATION" in os.environ:
            del os.environ["JUJU_RELATION"]

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

    def test_first_admin_not_created_without_name_email_password(self):
        """
        The first admin is not created when only one or two of name, email and
        password are given.
        """
        admins = [("Foo Bar", "foo@example.com", None),
                  ("Foo Bar", None, "secret"),
                  (None, "foo@example.com", "secret")]
        for name, email, password in admins:
            hooks.juju.config["admin-name"] = name
            hooks.juju.config["admin-email"] = email
            hooks.juju.config["admin-password"] = password
            self.assertFalse(hooks._create_first_admin())
            hooks.juju._logs = ()

    def test_first_admin_not_created_if_no_db_config(self):
        """
        The first administrator is not created if there is no database
        configuration in the service.conf file.
        """
        messages = ("First admin creation requested",
                    "No DB configuration yet, bailing.")
        hooks.juju.config["admin-name"] = "Foo Bar"
        hooks.juju.config["admin-email"] = "foo@example.com"
        hooks.juju.config["admin-password"] = "secret"
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["stores"] = {}
        config_obj.write()
        self.assertFalse(hooks._create_first_admin())
        self.assertEqual(messages, hooks.juju._logs)

    def test_email_syntax_check(self):
        """
        Invalid email addresses are flagged as such.
        """
        # some invalid choices
        emails = ["invalidemail", "invalid@", "a@b", "a@b.",
                  "`cat /etc/password`@example.com", "#foobar@example.com",
                  "(foo)@example.com", "foo@(example).com",
                  "'foo@example.com", "\"foo@example.com"]
        for email in emails:
            self.assertIs(False, hooks.util.is_email_valid(email))

    def test_create_landscape_admin_checks_email_syntax(self):
        """
        The util.create_landscape_admin() method verifies if the email is
        valid before attempting to create the admin.
        """
        db_user = "user"
        db_password = "password"
        db_host = "example.com"
        admin_name = "Foo Bar"
        admin_email = "foo'@bar"
        admin_password = "secret"

        account_is_empty = self.mocker.replace(hooks.util.account_is_empty)
        account_is_empty(db_user, db_password, db_host)
        self.mocker.result(True)
        self.mocker.replay()
        with unittest.TestCase.assertRaises(self, ValueError) as invalid_email:
            hooks.util.create_landscape_admin(db_user, db_password, db_host,
                                              admin_name, admin_email,
                                              admin_password)
        self.assertEqual("Invalid administrator email %s" % admin_email,
                         invalid_email.exception.message)

    def test_first_admin_not_created_if_account_not_empty(self):
        """
        The first administrator is not created if the account is not
        empty.
        """
        db_user = "user"
        db_password = "password"
        db_host = "example.com"
        admin_name = "Foo Bar"
        admin_email = "foo@example.com"
        admin_password = "secret"
        message = "DB not empty, skipping first admin creation"

        account_is_empty = self.mocker.replace(hooks.util.account_is_empty)
        account_is_empty(db_user, db_password, db_host)
        self.mocker.result(False)
        self.mocker.replay()
        admin_created = hooks.util.create_landscape_admin(
            db_user, db_password, db_host, admin_name, admin_email,
            admin_password)
        self.assertFalse(admin_created)
        self.assertEqual((message,), hooks.juju._logs)

    def test__create_first_admin_calls_create_landscape_admin(self):
        """
        When all conditions are met, _create_first_admin() calls
        create_landscape_admin.
        """
        # juju log message we expect
        message = "First admin creation requested"

        # we have an admin user defined
        admin_name = "Foo Bar"
        admin_email = "foo@example.com"
        admin_password = "secret"
        hooks.juju.config["admin-name"] = admin_name
        hooks.juju.config["admin-email"] = admin_email
        hooks.juju.config["admin-password"] = admin_password

        # we have the database access details
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        database = "mydb"
        db_host = "myhost"
        db_user = "myuser"
        db_password = "mypassword"
        stores = {"main": database, "host": db_host, "user": db_user,
                  "password": db_password}
        config_obj["stores"] = stores
        config_obj.write()

        # the db is up
        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up(database, db_host, db_user, db_password)
        self.mocker.result(True)

        # we can connect
        connect_exclusive = self.mocker.replace(hooks.util.connect_exclusive)
        connect_exclusive(db_host, db_user, db_password)
        connection = self.mocker.mock()
        self.mocker.result(connection)

        # util.create_landscape_admin is called
        create_landscape_admin = self.mocker.replace(
            hooks.util.create_landscape_admin)
        create_landscape_admin(
            db_user, db_password, db_host, admin_name, admin_email,
            admin_password)
        connection.close()
        self.mocker.replay()

        hooks._create_first_admin()
        self.assertEqual((message,), hooks.juju._logs)

    def test__create_first_admin_bails_if_db_is_not_up(self):
        """
        The _create_first_admin() method gives up if the DB is not
        accessible.
        """
        # juju log messages we expect
        messages = ("First admin creation requested",
                    "Can't talk to the DB yet, bailing.")
        # we have an admin user defined
        admin_name = "Foo Bar"
        admin_email = "foo@example.com"
        admin_password = "secret"
        hooks.juju.config["admin-name"] = admin_name
        hooks.juju.config["admin-email"] = admin_email
        hooks.juju.config["admin-password"] = admin_password

        # we have the database access details
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        database = "mydb"
        db_host = "myhost"
        db_user = "myuser"
        db_password = "mypassword"
        stores = {"main": database, "host": db_host, "user": db_user,
                  "password": db_password}
        config_obj["stores"] = stores
        config_obj.write()

        # the db is down, though
        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up(database, db_host, db_user, db_password)
        self.mocker.result(False)

        self.mocker.replay()
        admin_created = hooks._create_first_admin()
        self.assertFalse(admin_created)
        self.assertEqual(messages, hooks.juju._logs)

    def test__get_db_access_details(self):
        """
        The _get_db_access_details() function returns the database name and
        access details when all these keys exist in the landscape service
        configuration file.
        """
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        stores = {"main": "mydb", "host": "myhost", "user": "myuser",
                  "password": "mypassword"}
        config_obj["stores"] = stores
        config_obj.write()

        result = hooks._get_db_access_details()
        database, db_host, db_user, db_password = result
        self.assertEqual(database, stores["main"])
        self.assertEqual(db_host, stores["host"])
        self.assertEqual(db_user, stores["user"])
        self.assertEqual(db_password, stores["password"])

    def test_no_db_access_details_if_missing_config_key(self):
        """
        The _get_db_access_details() function returns None if any of
        the needed configuration keys is missing.
        """
        full_config = {"main": "mydb", "host": "myhost", "user": "myuser",
                       "password": "mypassword"}
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        # remove one key each time
        for key in full_config:
            data = full_config.copy()
            data.pop(key)
            config_obj["stores"] = data
            config_obj.write()
            result = hooks._get_db_access_details()
            self.assertIsNone(result)
        # last try, with no data at all
        config_obj.clear()
        config_obj.write()
        self.assertIsNone(hooks._get_db_access_details())

    def test_create_landscape_admin_calls_schema_script(self):
        """
        The create_landscape_admin() method calls the landscape schema
        script with the right parameters.
        """
        # we have an admin user defined
        admin_name = "Foo Bar"
        admin_email = "foo@example.com"
        admin_password = "secret"

        # juju log messages we expect
        messages = ("Creating first administrator",
                    "Administrator called %s with email %s created" %
                    (admin_name, admin_email))

        # we have the database access details
        db_host = "myhost"
        db_user = "myuser"
        db_password = "mypassword"

        # account is empty
        account_is_empty = self.mocker.replace(hooks.util.account_is_empty)
        account_is_empty(db_user, db_password, db_host)
        self.mocker.result(True)

        # schema script is called with the right parameters
        self.addCleanup(setattr, hooks.util.os, "environ",
                        hooks.util.os.environ)
        hooks.util.os.environ = {}
        env = {"LANDSCAPE_CONFIG": "standalone"}
        schema_call = self.mocker.replace(hooks.util.check_output)
        cmd = ["./schema", "--create-lds-account-only", "--admin-name",
               admin_name, "--admin-email", admin_email, "--admin-password",
               admin_password]
        schema_call(cmd, cwd="/opt/canonical/landscape", env=env)

        self.mocker.replay()

        hooks.util.create_landscape_admin(
            db_user, db_password, db_host, admin_name, admin_email,
            admin_password)
        self.assertEqual(messages, hooks.juju._logs)

    def test_get_services_non_proxied(self):
        """
        helper method should not break if non-proxied services are called for
        (e.g.: jobhandler).
        """
        hooks.juju.config["services"] = "jobhandler"
        result = hooks._get_services_haproxy()
        self.assertEqual(len(result), 0)

    def test_wb_get_installed_version_error_when_not_installed(self):
        """
        L{_get_installed_version} will report an error when the dpkg-query
        command fails due to specified package not being installed.
        """
        version_call = self.mocker.replace(hooks.check_output)
        version_call(
            ["dpkg-query", "--show", "--showformat=${Version}",
             "I-dont-exist"])
        self.mocker.throw(subprocess.CalledProcessError(1, "Command failed"))
        self.mocker.replay()

        result = hooks._get_installed_version("I-dont-exist")
        self.assertIsNone(result)
        message = (
            "Cannot determine version of I-dont-exist. Package is not "
            "installed.")
        self.assertIn(
            message, hooks.juju._logs, "Not logged- %s" % message)

    def test_wb_get_installed_version_success_when_installed(self):
        """
        When the requested package is installed, L{_get_installed_version} will
        return the package version as reported by the dpkg-query command.
        """
        version_call = self.mocker.replace(hooks.check_output)
        version_call(
            ["dpkg-query", "--show", "--showformat=${Version}",
             "I-exist"])
        self.mocker.result("1.2.3+456")
        self.mocker.replay()

        result = hooks._get_installed_version("I-exist")
        self.assertEqual("1.2.3+456", result)

    def test_wb_chown_sets_dir_and_file_ownership_to_landscape(self):
        """
        For a C{dir_path} specified, L{_chown} sets directory mode to 777 and
        ownership of the directory and all contained files to C{landscape} user
        and group.
        """

        class fake_pw_struct(object):
            """
            Fake both structs returned by getgrpnam and getpwnam for our needs
            """
            gr_gid = None
            pw_uid = None

            def __init__(self, value):
                self.gr_gid = value
                self.pw_uid = value

        dir_name = self.makeDir()
        with open("%s/anyfile" % dir_name, "w") as fp:
            fp.write("foobar")

        mode700 = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR
        mode777 = (
            mode700 | stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP |
            stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH)

        getpwnam = self.mocker.replace("pwd.getpwnam")
        getpwnam("landscape")
        self.mocker.result(fake_pw_struct(987))
        getpwnam = self.mocker.replace("grp.getgrnam")
        getpwnam("landscape")
        self.mocker.result(fake_pw_struct(989))
        chown = self.mocker.replace(os.chown)
        chown(dir_name, 987, 989)
        chown("%s/anyfile" % dir_name, 987, 989)
        self.mocker.replay()

        # Check initial file permissions and ownership
        mode = os.stat(dir_name).st_mode
        self.assertEqual(mode & mode700, mode700)
        self.assertNotEqual(mode & mode777, mode777)
        hooks._chown(dir_name)

        # Directory mode changed to 777 and gid/uid set
        mode = os.stat(dir_name).st_mode
        self.assertEqual(mode & mode777, mode777)

    def test_wb_create_maintenance_user_creates_on_lds_less_than_14_01(self):
        """
        C{landscape_maintenance} database user is created on installs with
        versions less than 14.01.
        """
        user = "landscape_maintenance"
        password = "asdf"
        host = "postgres/0"
        admin = "auto_db_admin"
        admin_password = "abc123"

        version_call = self.mocker.replace(hooks._get_installed_version)
        version_call("landscape-server")
        self.mocker.result("14.00+bzr1919")
        create_user = self.mocker.replace(hooks.util.create_user)
        create_user(user, password, host, admin, admin_password)
        self.mocker.replay()

        hooks._create_maintenance_user(password, host, admin, admin_password)
        message = "Creating landscape_maintenance user"
        self.assertIn(
            message, hooks.juju._logs, "Not logged- %s" % message)

    def test_wb_create_maintenance_user_not_created_if_lds_not_installed(self):
        """
        C{landscape_maintenance} database user is not created when we are
        unable to obtain installed version information for the landscape-server
        package.
        """
        user = "landscape_maintenance"
        password = "asdf"
        host = "postgres/0"
        admin = "auto_db_admin"
        admin_password = "abc123"

        version_call = self.mocker.replace(hooks._get_installed_version)
        version_call("landscape-server")
        self.mocker.result(None)  # No version info found (not installed)
        create_user = self.mocker.replace(hooks.util.create_user)
        create_user(user, password, host, admin, admin_password)
        self.mocker.count(0)
        self.mocker.replay()

        hooks._create_maintenance_user(password, host, admin, admin_password)

    def test_wb_create_maintenance_user_not_created_on_14_01(self):
        """
        C{landscape_maintenance} database user is not created on installs with
        versions 14.01 or greater.
        """
        user = "landscape_maintenance"
        password = "asdf"
        host = "postgres/0"
        admin = "auto_db_admin"
        admin_password = "abc123"

        version_call = self.mocker.replace(hooks._get_installed_version)
        version_call("landscape-server")
        self.mocker.result("14.01")
        create_user = self.mocker.replace(hooks.util.create_user)
        create_user(user, password, host, admin, admin_password)
        self.mocker.count(0)
        self.mocker.replay()

        hooks._create_maintenance_user(password, host, admin, admin_password)

    def test_amqp_relation_joined(self):
        """
        Ensure the amqp relation joined hook spits out settings when run.
        """
        hooks.amqp_relation_joined()
        baseline = {
            "username": "landscape",
            "vhost": "landscape"}
        self.assertEqual(baseline, dict(hooks.juju._outgoing_relation_data))

    def test_data_relation_changed_sets_mountpoint_awaits_init(self):
        """
        C{data-relation-changed} hook sends a requested C{mountpoint}
        to the storage subordinate charm. It will wait for the subordinate to
        respond with the initialised C{mountpoint} in the relation before
        acting.
        """
        self.assertRaises(SystemExit, hooks.data_relation_changed)
        baseline = {"mountpoint": "/srv/juju/vol-0001"}
        self.assertEqual(baseline, dict(hooks.juju._outgoing_relation_data))
        messages = ["External storage relation changed: requesting mountpoint "
                    "%s from storage charm" % hooks.STORAGE_MOUNTPOINT,
                    "Awaiting storage mountpoint intialisation from storage "
                    "relation"]
        for message in messages:
            self.assertIn(
                message, hooks.juju._logs, "Not logged- %s" % message)

    def test_data_relation_changed_error_on_mountpoint_from_subordinate(self):
        """
        C{data-relation-changed} will exit in error if the C{mountpoint} set
        from the subordinate charm relation does not exist.
        """
        hooks.juju._incoming_relation_data = (
            ("mountpoint", hooks.STORAGE_MOUNTPOINT),)

        self.assertEqual(
            hooks.juju.relation_get("mountpoint"), hooks.STORAGE_MOUNTPOINT)

        exists = self.mocker.replace(os.path.exists)
        exists(hooks.STORAGE_MOUNTPOINT)
        self.mocker.result(False)
        self.mocker.replay()

        self.assertRaises(SystemExit, hooks.data_relation_changed)
        message = (
            "Error: Mountpoint %s doesn't appear to exist" %
            hooks.STORAGE_MOUNTPOINT)
        self.assertIn(
            message, hooks.juju._logs, "Not logged- %s" % message)

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
        self.assertIn(message, hooks.juju._logs, "Not logged; %s" % message)

    def test_data_relation_changed_success_no_repository_path(self):
        """
        When no repository path directory is discovered,
        L{data_relation_changed} will log that no repository info is migrated.
        Finally L{data_relation_changed} will call L{config-changed} to ensure
        landscape services are restarted to reload the changes.
        """
        self.addCleanup(setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = (
            ("mountpoint", hooks.STORAGE_MOUNTPOINT),)
        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        new_log_path = "/srv/juju/vol-0001/landscape/1/logs"
        new_repo_path = "/srv/juju/vol-0001/landscape-repository"

        exists = self.mocker.replace(os.path.exists)
        exists(hooks.STORAGE_MOUNTPOINT)
        self.mocker.result(True)
        exists(new_log_path)
        self.mocker.result(True)
        exists(new_repo_path)
        self.mocker.result(True)
        lsctl = self.mocker.replace(hooks._lsctl)
        lsctl("stop")
        check_call_mock = self.mocker.replace(subprocess.check_call)
        check_call_mock(
            "cp -f /some/log/path/*log %s" % new_log_path, shell=True)
        _chown = self.mocker.replace(hooks._chown)
        _chown(new_log_path)
        exists("/some/repository/path")
        self.mocker.result(False)
        config_changed = self.mocker.replace(hooks.config_changed)
        config_changed()
        self.mocker.replay()

        # Setup sample config file values
        data = [("global", "oops-path", "/some/oops/path"),
                ("global", "log-path", "/some/log/path"),
                ("landscape", "repository-path", "/some/repository/path")]

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["global"] = {}
        config_obj["landscape"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)

        hooks.data_relation_changed()

        # Refresh the config_obj to read config changes
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(
            config_obj["landscape"]["repository-path"], new_repo_path)
        self.assertEqual(config_obj["global"]["log-path"], new_log_path)
        self.assertEqual(config_obj["global"]["oops-path"], new_log_path)

        messages = ["Migrating log data to %s" % new_log_path,
                    "No repository data migrated"]
        for message in messages:
            self.assertIn(
                message, hooks.juju._logs, "Not logged- %s" % message)

    def test_data_relation_changed_success_no_repository_data(self):
        """
        L{data_relation_changed} will migrate existing logs to the new
        C{mountpoint} and update paths in C{LANDSCAPE_SERVICE_CONF} for the
        following configuration settings: C{repository-path}, C{log-path} and
        C{oops-path}. When no repository data is discovered,
        L{data_relation_changed} will log that info.
        Finally L{data_relation_changed} will call L{config-changed} to ensure
        landscape services are restarted to reload the changes.
        """
        self.addCleanup(setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = (
            ("mountpoint", hooks.STORAGE_MOUNTPOINT),)
        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        new_log_path = "/srv/juju/vol-0001/landscape/1/logs"
        new_repo_path = "/srv/juju/vol-0001/landscape-repository"

        exists = self.mocker.replace(os.path.exists)
        exists(hooks.STORAGE_MOUNTPOINT)
        self.mocker.result(True)
        exists(new_log_path)
        self.mocker.result(True)
        exists(new_repo_path)
        self.mocker.result(True)
        lsctl = self.mocker.replace(hooks._lsctl)
        lsctl("stop")
        check_call_mock = self.mocker.replace(subprocess.check_call)
        check_call_mock(
            "cp -f /some/log/path/*log %s" % new_log_path, shell=True)
        _chown = self.mocker.replace(hooks._chown)
        _chown(new_log_path)
        exists("/some/repository/path")
        self.mocker.result(True)
        listdir = self.mocker.replace(os.listdir)
        listdir("/some/repository/path")
        self.mocker.result([])
        config_changed = self.mocker.replace(hooks.config_changed)
        config_changed()
        self.mocker.replay()

        # Setup sample config file values
        data = [("global", "oops-path", "/some/oops/path"),
                ("global", "log-path", "/some/log/path"),
                ("landscape", "repository-path", "/some/repository/path")]

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["global"] = {}
        config_obj["landscape"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)

        hooks.data_relation_changed()

        # Refresh the config_obj to read config changes
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(
            config_obj["landscape"]["repository-path"], new_repo_path)
        self.assertEqual(config_obj["global"]["log-path"], new_log_path)
        self.assertEqual(config_obj["global"]["oops-path"], new_log_path)

        messages = ["Migrating log data to %s" % new_log_path,
                    "No repository data migrated"]
        for message in messages:
            self.assertIn(
                message, hooks.juju._logs, "Not logged- %s" % message)

    def test_data_relation_changed_success_with_repository_data(self):
        """
        L{data_relation_changed} will migrate existing logs and respository
        data to the new C{mountpoint} and update paths in
        C{LANDSCAPE_SERVICE_CONF} for the following configuration settings:
        C{repository-path}, C{log-path} and C{oops-path}.
        """
        self.addCleanup(setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = (
            ("mountpoint", hooks.STORAGE_MOUNTPOINT),)
        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        new_log_path = "/srv/juju/vol-0001/landscape/1/logs"
        new_repo_path = "/srv/juju/vol-0001/landscape-repository"

        exists = self.mocker.replace(os.path.exists)
        exists(hooks.STORAGE_MOUNTPOINT)
        self.mocker.result(True)
        exists(new_log_path)
        self.mocker.result(True)
        exists(new_repo_path)
        self.mocker.result(True)
        lsctl = self.mocker.replace(hooks._lsctl)
        lsctl("stop")
        self.mocker.count(3)   # 1 for log migration, repo, and config changed
        check_call_mock = self.mocker.replace(subprocess.check_call)
        check_call_mock(
            "cp -f /some/log/path/*log %s" % new_log_path, shell=True)
        _chown = self.mocker.replace(hooks._chown)
        _chown(new_log_path)
        exists("/some/repository/path")
        self.mocker.result(True)
        listdir = self.mocker.replace(os.listdir)
        listdir("/some/repository/path")
        self.mocker.result(["one-repo-dir"])
        check_call_mock(
            "cp -r /some/repository/path/* %s" % new_repo_path, shell=True)
        self.mocker.replay()

        # Setup sample config file values
        data = [("global", "oops-path", "/some/oops/path"),
                ("global", "log-path", "/some/log/path"),
                ("landscape", "repository-path", "/some/repository/path")]

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["global"] = {}
        config_obj["landscape"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)

        hooks.data_relation_changed()

        # Refresh the config_obj to read config changes
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(
            config_obj["landscape"]["repository-path"], new_repo_path)
        self.assertEqual(config_obj["global"]["log-path"], new_log_path)
        self.assertEqual(config_obj["global"]["oops-path"], new_log_path)

        messages = ["Migrating log data to %s" % new_log_path,
                    "Migrating repository data to %s" % new_repo_path]
        for message in messages:
            self.assertIn(
                message, hooks.juju._logs, "Not logged- %s" % message)

    def test_data_relation_changed_creates_new_log_and_repository_paths(self):
        """
        L{data_relation_changed} will create the new shared log and repository
        data paths if they don't exist during the log and data migration.
        """
        self.addCleanup(setattr, hooks.juju, "_incoming_relation_data", ())
        hooks.juju._incoming_relation_data = (
            ("mountpoint", hooks.STORAGE_MOUNTPOINT),)
        self.addCleanup(setattr, hooks.os, "environ", hooks.os.environ)
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/1"}

        new_log_path = "/srv/juju/vol-0001/landscape/1/logs"
        new_repo_path = "/srv/juju/vol-0001/landscape-repository"

        exists = self.mocker.replace(os.path.exists)
        exists(hooks.STORAGE_MOUNTPOINT)
        self.mocker.result(True)
        exists(new_log_path)
        self.mocker.result(False)
        makedirs = self.mocker.replace(os.makedirs)
        makedirs(new_log_path)
        lsctl = self.mocker.replace(hooks._lsctl)
        lsctl("stop")
        self.mocker.count(3)
        check_call_mock = self.mocker.replace(subprocess.check_call)
        check_call_mock(
            "cp -f /some/log/path/*log %s" % new_log_path, shell=True)
        _chown = self.mocker.replace(hooks._chown)
        _chown(new_log_path)
        exists(new_repo_path)
        self.mocker.result(False)
        makedirs(new_repo_path)
        _chown(new_repo_path, owner="root")
        exists("/some/repository/path")
        self.mocker.result(True)
        listdir = self.mocker.replace(os.listdir)
        listdir("/some/repository/path")
        self.mocker.result(["one-repo-dir"])
        check_call_mock(
            "cp -r /some/repository/path/* %s" % new_repo_path, shell=True)
        self.mocker.replay()

        # Setup sample config file values
        data = [("global", "oops-path", "/some/oops/path"),
                ("global", "log-path", "/some/log/path"),
                ("landscape", "repository-path", "/some/repository/path")]

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["global"] = {}
        config_obj["landscape"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)

        hooks.data_relation_changed()

        # Refresh the config_obj to read config changes
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(
            config_obj["landscape"]["repository-path"], new_repo_path)
        self.assertEqual(config_obj["global"]["log-path"], new_log_path)
        self.assertEqual(config_obj["global"]["oops-path"], new_log_path)

        messages = ["Migrating log data to %s" % new_log_path,
                    "Migrating repository data to %s" % new_repo_path]
        for message in messages:
            self.assertIn(
                message, hooks.juju._logs, "Not logged- %s" % message)

    def test__download_file_success(self):
        """
        Make sure the happy path of download file works.
        """
        filename = self.makeFile()
        with open(filename, "w") as fp:
            fp.write("foobar")
        output = hooks._download_file("file:///%s" % filename)
        self.assertIn("foobar", output)

    def test__download_file_success_trailing_newline(self):
        """Test that newlines are stripped before passing to curl. CVE-2014-8150."""
        # put two newlines, since that could be a common pattern in a text
        # file when using an editor
        hooks._download_file("http://example.com/\n\n", Curl=CurlStub)
        self.assertEqual(["http://example.com/"], CurlStub.urls)

    def test__download_file_failure(self):
        """The fail path of download file raises an exception."""
        self.assertRaises(
            pycurl.error, hooks._download_file, "file:///FOO/NO/EXIST")

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
        """Install a license from a string."""
        hooks._install_license()
        self.assertFileContains(
            hooks.LANDSCAPE_LICENSE_DEST, "LICENSE_FILE_TEXT")

    def test__install_license_url(self):
        """Install a license from a url."""
        source = self.makeFile()
        with open(source, "w") as fp:
            fp.write("LICENSE_FILE_TEXT from curl")
        hooks.juju.config["license-file"] = "file:///%s" % source
        hooks._install_license()
        self.assertFileContains(
            hooks.LANDSCAPE_LICENSE_DEST, "LICENSE_FILE_TEXT from curl")

    def test_handle_no_license(self):
        """Don't try to install the license when none was given."""
        hooks.juju.config["license-file"] = None
        hooks._install_license()
        self.assertFalse(os.path.exists(hooks.LANDSCAPE_LICENSE_DEST))

    def test_handle_empty_license(self):
        """Don't try to install the license when it's empty."""
        hooks.juju.config["license-file"] = ""
        hooks._install_license()
        self.assertFalse(os.path.exists(hooks.LANDSCAPE_LICENSE_DEST))

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

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["stores"] = {}
        config_obj["schema"] = {}
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)
        new_user = "landscape"
        new_password = "def456"
        host = "postgres/0"
        admin = "auto_db_admin"
        password = "abc123"

        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("postgres", host, admin, password)
        self.mocker.result(True)
        connect_exclusive = self.mocker.replace(hooks.util.connect_exclusive)
        connect_exclusive(host, admin, password)
        connection = self.mocker.mock()
        self.mocker.result(connection)
        create_user = self.mocker.replace(hooks.util.create_user)
        create_user(new_user, new_password, host, admin, password)
        check_call = self.mocker.replace(hooks.check_call)
        check_call("setup-landscape-server")
        maintenance_mock = self.mocker.replace(hooks._create_maintenance_user)
        maintenance_mock(new_password, host, admin, password)
        connection.close()
        vhost_changed = self.mocker.replace(
            hooks.vhost_config_relation_changed)
        vhost_changed()
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

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(config_obj.keys(), [])

    def test_db_admin_relation_changed_no_config_if_db_down(self):
        """
        db_admin_relation_changed does not update the service configuration
        file if is_db_up() returns False.
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
        hooks.os.environ = {"JUJU_UNIT_NAME": "landscape/0"}

        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("postgres", "postgres/0", "auto_db_admin", "abc123")
        self.mocker.result(False)
        self.mocker.replay()
        hooks.db_admin_relation_changed()

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(config_obj.keys(), [])

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

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(config_obj.keys(), [])

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

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(config_obj.keys(), [])

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

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(config_obj.keys(), [])

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

        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        self.assertEqual(config_obj.keys(), [])

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
        message = "Putting unit into maintenance mode"
        self.assertIn(
            message, hooks.juju._logs, "Not logged- %s" % message)

    def test_maintenance_file_only_removed_if_db_and_amqp_are(self):
        """
        When maintenance flag is set C{False} and both the database and amqp
        are accessible, the maintenance file will be removed.
        """
        hooks.LANDSCAPE_MAINTENANCE = self.makeFile()
        hooks.juju.config["maintenance"] = True
        hooks._set_maintenance()  # Create the maintenance file
        data = [("stores", "main", "somedb"),
                ("stores", "host", "somehost"),
                ("stores", "user", "someuser"),
                ("stores", "password", "somepassword")]
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["stores"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.write()
        hooks.juju.config["maintenance"] = False
        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("somedb", "somehost", "someuser", "somepassword")
        self.mocker.result(True)
        is_amqp_up = self.mocker.replace(hooks._is_amqp_up)
        is_amqp_up()
        self.mocker.result(True)
        self.mocker.replay()

        hooks._set_maintenance()
        self.assertFalse(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))
        message = "Remove unit from maintenance mode"
        self.assertIn(
            message, hooks.juju._logs, "Not logged- %s" % message)

    def test_maintenance_file_not_removed_if_db_is_not_up(self):
        """
        When maintenance flag is set C{False} and the database is not
        accessible, the maintenance file will not be removed.
        """
        hooks.LANDSCAPE_MAINTENANCE = self.makeFile()
        hooks.juju.config["maintenance"] = True
        hooks._set_maintenance()  # Create the maintenance file

        hooks.juju.config["maintenance"] = False
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(False)
        self.mocker.replay()

        hooks._set_maintenance()
        self.assertTrue(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))

    def test_maintenance_file_not_removed_if_amqp_is_not_up(self):
        """
        When maintenance flag is set C{False} and the AMQP service is not
        accessible, the maintenance file will not be removed.
        """
        hooks.LANDSCAPE_MAINTENANCE = self.makeFile()
        hooks.juju.config["maintenance"] = True
        hooks._set_maintenance()  # Create the maintenance file

        hooks.juju.config["maintenance"] = False
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(True)
        is_amqp_up = self.mocker.replace(hooks._is_amqp_up)
        is_amqp_up()
        self.mocker.result(False)
        self.mocker.replay()

        hooks._set_maintenance()
        self.assertTrue(os.path.exists(hooks.LANDSCAPE_MAINTENANCE))

    def test_is_db_up_with_db_configured(self):
        """Return True when the db is configured."""
        data = [("stores", "main", "somedb"),
                ("stores", "host", "somehost"),
                ("stores", "user", "someuser"),
                ("stores", "password", "somepassword")]
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["stores"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)

        is_db_up = self.mocker.replace(hooks.util.is_db_up)
        is_db_up("somedb", "somehost", "someuser", "somepassword")
        self.mocker.result(True)
        self.mocker.replay()

        self.assertTrue(hooks._is_db_up())

    def test_is_db_up_db_not_configured(self):
        """Return False when the db is not configured."""
        data = [("stores", "main", "somedb"),
                ("stores", "host", "somehost"),
                ("stores", "user", "someuser"),
                ("stores", "password", "somepassword")]
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["stores"] = {}
        for section, key, value in data:
            config_obj[section][key] = value
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
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
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)
        self.assertFalse(hooks._is_db_up())

    def test_is_db_up_service_config_missing_keys(self):
        """Return False when the [stores] section is missing db settings."""
        config_obj = ConfigObj(hooks.LANDSCAPE_SERVICE_CONF)
        config_obj["stores"] = {}
        config_obj.filename = hooks.LANDSCAPE_SERVICE_CONF
        config_obj.write()
        self._service_conf.seek(0)
        self.assertFalse(hooks._is_db_up())

    def test__get_haproxy_service_name(self):
        """
        _get_haproxy_service_name() returns the jinja-ready service name used
        to deploy haproxy.
        """
        haproxy_service_name = hooks._get_haproxy_service_name()
        self.assertEqual(haproxy_service_name, "landscapehaproxy")

    def test_no_haproxy_service_name_if_not_related_to_haproxy(self):
        """
        _get_haproxy_service_name() returns None if we are not related to
        haproxy.
        """
        def no_website_relation(relation_name):
            return None

        self.addCleanup(setattr, hooks.juju, "relation_ids",
                        hooks.juju.relation_ids)
        hooks.juju.relation_ids = no_website_relation
        haproxy_service_name = hooks._get_haproxy_service_name()
        self.assertIsNone(haproxy_service_name)

    def test_no_haproxy_service_name_if_no_units_in_relation(self):
        """
        _get_haproxy_service_name() returns None if we are related to haproxy,
        but that relation has no units.
        """
        def no_units(relation_id):
            return []

        self.addCleanup(setattr, hooks.juju, "relation_list",
                        hooks.juju.relation_list)
        hooks.juju.relation_list = no_units
        haproxy_service_name = hooks._get_haproxy_service_name()
        self.assertIsNone(haproxy_service_name)

    def test__get_vhost_template(self):
        """
        The haproxy prefix in the template variables is replaced by the
        name of the actual haproxy service that is part of the deployment.
        """
        template_file = "vhostssl.tmpl"
        with open("%s/config/%s" % (hooks.ROOT, template_file), "r") as t:
            original_template = t.read()
        new_template = hooks._get_vhost_template(template_file,
                                                 "landscape-haproxy")
        self.assertIn("{{ haproxy_msgserver }}", original_template)
        self.assertNotIn("{{ landscape-haproxy_msgserver }}",
                         original_template)
        self.assertIn("{{ landscape-haproxy_msgserver }}", new_template)


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

    def test_notify_vhost_config_relation_specify_id(self):
        """
        notify the vhost-config relation on a separate ID.
        """
        hooks.notify_vhost_config_relation("haproxy", "foo/0")
        with open("%s/config/vhostssl.tmpl" % hooks.ROOT, 'r') as f:
            vhostssl_template = f.read()
        with open("%s/config/vhost.tmpl" % hooks.ROOT, 'r') as f:
            vhost_template = f.read()
        baseline = yaml.dump(
            [{"port": "443", "template": base64.b64encode(vhostssl_template)},
             {"port": "80", "template": base64.b64encode(vhost_template)}])
        self.assertEqual(
            (("vhosts", baseline),), hooks.juju._outgoing_relation_data)

    def test_notify_vhost_config_relation_legacy_template(self):
        """
        If the landscape-server package being installed has offline pages
        under the static dir, the legacy templates are used.
        """
        self.addCleanup(
            setattr, hooks, "HAS_OLD_ERROR_PATH", hooks.HAS_OLD_ERROR_PATH)
        hooks.HAS_OLD_ERROR_PATH = True
        hooks.notify_vhost_config_relation("haproxy", "foo/0")
        with open("%s/config/vhostssl.tmpl.legacy" % hooks.ROOT, 'r') as f:
            vhostssl_template = f.read()
        with open("%s/config/vhost.tmpl.legacy" % hooks.ROOT, 'r') as f:
            vhost_template = f.read()
        baseline = yaml.dump(
            [{"port": "443", "template": base64.b64encode(vhostssl_template)},
             {"port": "80", "template": base64.b64encode(vhost_template)}])
        self.assertEqual(
            (("vhosts", baseline),), hooks.juju._outgoing_relation_data)

    def test_notify_vhost_config_relation(self):
        """notify the vhost-config relation on the "current" ID."""
        hooks.notify_vhost_config_relation("haproxy")
        with open("%s/config/vhostssl.tmpl" % hooks.ROOT, 'r') as f:
            vhostssl_template = f.read()
        with open("%s/config/vhost.tmpl" % hooks.ROOT, 'r') as f:
            vhost_template = f.read()
        baseline = yaml.dump(
            [{"port": "443", "template": base64.b64encode(vhostssl_template)},
             {"port": "80", "template": base64.b64encode(vhost_template)}])
        self.assertEqual(
            (("vhosts", baseline),), hooks.juju._outgoing_relation_data)

    def test_vhost_config_relation_changed_exit_no_configuration(self):
        """Ensure vhost_relation_changed deferrs if db is not up."""
        os.environ["JUJU_RELATION"] = "vhost-config"
        self.assertRaises(SystemExit, hooks.vhost_config_relation_changed)
        self.assertEquals(len(hooks.juju._logs), 1)
        self.assertIn('Database not ready yet', hooks.juju._logs[0])

    def test_vhost_config_relation_changed_wait_apache_servername(self):
        """Ensure vhost_relation_changed deferrs if db is not up."""
        os.environ["JUJU_RELATION"] = "vhost-config"
        _get_config_obj = self.mocker.replace(hooks._get_config_obj)
        _get_config_obj(hooks.LANDSCAPE_SERVICE_CONF)
        self.mocker.result({
            "stores": {
                "main": "database",
                "host": "host",
                "user": "user",
                "password": "password"}})
        notify_vhost = self.mocker.replace(hooks.notify_vhost_config_relation)
        notify_vhost(hooks._get_haproxy_service_name(), None)
        self.mocker.replay()
        self.assertRaises(SystemExit, hooks.vhost_config_relation_changed)
        self.assertIn('Waiting for data from apache', hooks.juju._logs[-1])

    def test_vhost_config_relation_changed_fail_root_url(self):
        """Ensure vhost_relation_changed deferrs if db is not up."""
        os.environ["JUJU_RELATION"] = "vhost-config"
        _get_config_obj = self.mocker.replace(hooks._get_config_obj)
        _get_config_obj(hooks.LANDSCAPE_SERVICE_CONF)
        hooks.juju._incoming_relation_data += (("servername", "foobar"),)
        self.mocker.result({
            "stores": {
                "main": "database",
                "host": "host",
                "user": "user",
                "password": "password"}})
        notify_vhost = self.mocker.replace(hooks.notify_vhost_config_relation)
        notify_vhost(hooks._get_haproxy_service_name(), None)
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(False)
        self.mocker.replay()
        self.assertRaises(SystemExit, hooks.vhost_config_relation_changed)
        self.assertIn(
            'Waiting for database to become available, deferring',
            hooks.juju._logs[-1])

    def test_vhost_config_relation_changed_fail_root_url_db_update(self):
        """vhost_config_relation_changed should error if db update fails"""
        os.environ["JUJU_RELATION"] = "vhost-config"
        _get_config_obj = self.mocker.replace(hooks._get_config_obj)
        _get_config_obj(hooks.LANDSCAPE_SERVICE_CONF)
        hooks.juju._incoming_relation_data += (("servername", "foobar"),)
        self.mocker.result({
            "stores": {
                "main": "database",
                "host": "host",
                "user": "user",
                "password": "password"}})
        notify_vhost = self.mocker.replace(hooks.notify_vhost_config_relation)
        notify_vhost(hooks._get_haproxy_service_name(), None)
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(True)
        self.mocker.replay()
        self.assertRaises(psycopg2.Error, hooks.vhost_config_relation_changed)

    def test_vhost_config_relation_changed_cert_not_provided(self):
        """
        Ensure vhost_relation_changed runs to completion.

        Existing cert should be removed.
        """
        os.environ["JUJU_RELATION"] = "vhost-config"
        hooks.SSL_CERT_LOCATION = tempfile.NamedTemporaryFile().name
        _get_config_obj = self.mocker.replace(hooks._get_config_obj)
        _get_config_obj(hooks.LANDSCAPE_SERVICE_CONF)
        hooks.juju._incoming_relation_data += (("servername", "foobar"),)
        self.mocker.result({
            "stores": {
                "main": "database",
                "host": "host",
                "user": "user",
                "password": "password"}})
        notify_vhost = self.mocker.replace(hooks.notify_vhost_config_relation)
        notify_vhost(hooks._get_haproxy_service_name(), None)
        mock_conn = self.mocker.mock()
        mock_conn.close()
        connect_exclusive = self.mocker.replace(hooks.util.connect_exclusive)
        connect_exclusive("host", "user", "password")
        self.mocker.result(mock_conn)
        change_root_url = self.mocker.replace(hooks.util.change_root_url)
        change_root_url(
            "database", "user", "password", "host", "https://foobar/")
        config_changed = self.mocker.replace(hooks.config_changed)
        config_changed()
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(True)
        self.mocker.replay()
        hooks.vhost_config_relation_changed()
        self.assertFalse(os.path.exists(hooks.SSL_CERT_LOCATION))

    def test_vhost_config_relation_changed_ssl_cert_provided(self):
        """
        Ensure vhost_relation_changed runs to completion.

        Cert passed in to other side of relation should be written on disk.
        """
        os.environ["JUJU_RELATION"] = "vhost-config"
        hooks.SSL_CERT_LOCATION = tempfile.NamedTemporaryFile().name
        _get_config_obj = self.mocker.replace(hooks._get_config_obj)
        _get_config_obj(hooks.LANDSCAPE_SERVICE_CONF)
        hooks.juju._incoming_relation_data += (("servername", "foobar"),)
        hooks.juju._incoming_relation_data += (
            ("ssl_cert", base64.b64encode("foobar")),)
        self.mocker.result({
            "stores": {
                "main": "database",
                "host": "host",
                "user": "user",
                "password": "password"}})
        notify_vhost = self.mocker.replace(hooks.notify_vhost_config_relation)
        notify_vhost(hooks._get_haproxy_service_name(), None)
        is_db_up = self.mocker.replace(hooks._is_db_up)
        is_db_up()
        self.mocker.result(True)
        mock_conn = self.mocker.mock()
        mock_conn.close()
        connect_exclusive = self.mocker.replace(hooks.util.connect_exclusive)
        connect_exclusive("host", "user", "password")
        self.mocker.result(mock_conn)
        change_root_url = self.mocker.replace(hooks.util.change_root_url)
        change_root_url(
            "database", "user", "password", "host", "https://foobar/")
        config_changed = self.mocker.replace(hooks.config_changed)
        config_changed()
        self.mocker.replay()
        hooks.vhost_config_relation_changed()
        self.assertTrue(os.path.exists(hooks.SSL_CERT_LOCATION))
        with open(hooks.SSL_CERT_LOCATION, 'r') as f:
            self.assertEqual("foobar", f.read())

    def test_vhost_config_relation_exits_if_haproxy_not_ready(self):
        """
        notify_vhost_config_relation() is not called if the haproxy relation
        is not there.
        """
        def should_not_be_here(*args):
            raise AssertionError("notify_vhost_config_relation() should not "
                                 "be called")

        self.addCleanup(setattr, hooks, "vhost_config_relation_changed",
                        hooks.vhost_config_relation_changed)
        hooks.notify_vhost_config_relation = should_not_be_here
        get_haproxy_service_name = self.mocker.replace(
            hooks._get_haproxy_service_name)
        get_haproxy_service_name()
        self.mocker.result(None)
        self.mocker.replay()
        hooks.vhost_config_relation_changed()


class TestHooksUtils(TestHooks):

    def test__setup_apache(self):
        """
        Responsible for setting up apache to serve static content.
        - various 'a2*' commands need to be mocked and tested to ensure
          proper parameters are passed.
        - make sure we actually replace '@hostname@' with 'localhost' in the
          site file we are installing.
        - ensure new file has '.conf' extension.
        """
        tempdir = self.makeDir()
        with open("%s/default.random_extension" % tempdir, 'w') as f:
            f.write("HI!")
        with open("%s/default2.conf" % tempdir, 'w') as f:
            f.write("HI!")
        # Replace dir, but leave basename to check that it has '.conf'
        # (new requirement with Trusty apache2)
        site_file = os.path.basename(hooks.LANDSCAPE_APACHE_SITE)
        hooks.LANDSCAPE_APACHE_SITE = "%s/%s" % (tempdir, site_file)
        _a2enmods = self.mocker.replace(hooks._a2enmods)
        _a2dissite = self.mocker.replace(hooks._a2dissite)
        _a2ensite = self.mocker.replace(hooks._a2ensite)
        _service = self.mocker.replace(hooks._service)
        _a2enmods(["rewrite", "proxy_http", "ssl", "headers", "expires"])
        _a2dissite("default.random_extension")
        _a2dissite("default2.conf")
        _a2ensite("landscape.conf")
        _service("apache2", "restart")
        self.mocker.replay()
        hooks._setup_apache()
        self.assertTrue(os.path.exists("%s/landscape.conf" % tempdir))
        with open("%s/landscape.conf" % tempdir, 'r') as f:
            site_text = f.read()
        self.assertFalse("@hostname@" in site_text)
        self.assertTrue("localhost" in site_text)
        self.assertTrue("/offline/unauthorized.html" in site_text)

    def test__setup_apache_legacy(self):
        """
        Use ".legacy" apache templates if the location of offline packages
        is under the old static directory.
        """
        self.addCleanup(
            setattr, hooks, "HAS_OLD_ERROR_PATH", hooks.HAS_OLD_ERROR_PATH)
        hooks.HAS_OLD_ERROR_PATH = True
        tempdir = self.makeDir()
        with open("%s/default.random_extension" % tempdir, 'w') as f:
            f.write("HI!")
        with open("%s/default2.conf" % tempdir, 'w') as f:
            f.write("HI!")
        # Replace dir, but leave basename to check that it has '.conf'
        # (new requirement with Trusty apache2)
        site_file = os.path.basename(hooks.LANDSCAPE_APACHE_SITE)
        hooks.LANDSCAPE_APACHE_SITE = "%s/%s" % (tempdir, site_file)
        _a2enmods = self.mocker.replace(hooks._a2enmods)
        _a2dissite = self.mocker.replace(hooks._a2dissite)
        _a2ensite = self.mocker.replace(hooks._a2ensite)
        _service = self.mocker.replace(hooks._service)
        _a2enmods(["rewrite", "proxy_http", "ssl", "headers", "expires"])
        _a2dissite("default.random_extension")
        _a2dissite("default2.conf")
        _a2ensite("landscape.conf")
        _service("apache2", "restart")
        self.mocker.replay()
        hooks._setup_apache()
        self.assertTrue(os.path.exists("%s/landscape.conf" % tempdir))
        with open("%s/landscape.conf" % tempdir, 'r') as f:
            site_text = f.read()
        self.assertIn("/static/offline/unauthorized.html", site_text)
