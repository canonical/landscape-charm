from fixtures import EnvironmentVariable

from charmhelpers.core.services.base import ServiceManager

from lib.paths import LSCTL, SCHEMA_SCRIPT
from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.utils import update_persisted_data
from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.tests.sample import SAMPLE_DB_UNIT_DATA


class SchemaBootstrapTest(HookenvTest):

    with_hookenv_monkey_patching = True

    def setUp(self):
        super(SchemaBootstrapTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.manager = ServiceManager(services=[{"service": "landscape"}])
        self.callback = SchemaBootstrap(subprocess=self.subprocess)

    def test_options(self):
        """
        The schema script is invoked with the --bootstrap option and the proxy
        options.
        """
        self.callback(self.manager, "landscape", None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap"],
            self.subprocess.calls[0][0])

    def test_with_proxy_settings(self):
        """
        The proxy options are set according to the environment variables.
        """
        self.useFixture(EnvironmentVariable("http_proxy", "http://host:3128"))
        self.useFixture(EnvironmentVariable("https_proxy", "http://host:3128"))
        self.useFixture(EnvironmentVariable("no_proxy", "localhost"))
        self.callback(self.manager, "landscape", None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap",
             "--with-http-proxy=http://host:3128",
             "--with-https-proxy=http://host:3128",
             "--with-no-proxy=localhost"],
            self.subprocess.calls[0][0])

    def test_was_ready(self):
        """
        If the services was ready, the schema script is not invoked again.
        """
        self.manager.save_ready("landscape")
        self.callback(self.manager, "landscape", None)
        self.assertEqual([], self.subprocess.calls)


class LSCtlTest(HookenvTest):

    with_hookenv_monkey_patching = True

    def setUp(self):
        super(LSCtlTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(LSCTL)
        self.services = [{
            "service": "landscape",
            "required_data": [{"db": [SAMPLE_DB_UNIT_DATA]}]}]
        self.manager = ServiceManager(services=self.services)
        self.callback = LSCtl(subprocess=self.subprocess, hookenv=self.hookenv)

    def test_start(self):
        """
        The 'lsctl' script is invoked with the 'restart' action if the event
        name is 'start'.
        """
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_stop(self):
        """
        The 'lsctl' script is invoked with the 'stop' action if the event name
        is 'stop'.
        """
        self.callback(self.manager, "landscape", "stop")
        self.assertEqual(
            ["/usr/bin/lsctl", "stop"], self.subprocess.calls[0][0])

    def test_config_changed_only_apt(self):
        """
        The 'lsctl' script is not invoked if only the APT source has changed.
        """
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config["source"] = "ppa:landscape/15.01"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual([], self.subprocess.calls)

    def test_config_changed_not_only_apt(self):
        """
        The 'lsctl' script is invoked if not only the APT source has changed.
        """
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config["license-file"] = "<old data>"
        config.save()
        config["source"] = "ppa:landscape/15.01"
        config["license-file"] = "<new data>"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_config_changed_only_ssl(self):
        """
        The 'lsctl' script is not invoked if only the SSL certificate has
        changed.
        """
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["ssl-cert"] = "<old-cert>"
        config["ssl-key"] = "<old-key>"
        config.save()
        config["ssl-cert"] = "<new-cert>"
        config["ssl-key"] = "<new-key>"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual([], self.subprocess.calls)

    def test_db_connection_details_first_time(self):
        """
        The 'lsctl' script is invoked if no db connection details where
        available yet.
        """
        self.hookenv.hook = "db-relation-changed"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_db_connection_details_are_saved(self):
        """
        The LSCtl callback always saves the current db connection details.
        """
        self.hookenv.hook = "random-hook"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])
        self.assertEqual(
            SAMPLE_DB_UNIT_DATA,
            update_persisted_data("db", None, hookenv=self.hookenv))

    def test_db_connection_details_unchanged(self):
        """
        The 'lsctl' script is not invoked if db connection details are
        unchanged.
        """
        update_persisted_data("db", SAMPLE_DB_UNIT_DATA, hookenv=self.hookenv)
        self.hookenv.hook = "db-relation-changed"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual([], self.subprocess.calls)

    def test_db_connection_details_changed(self):
        """
        The 'lsctl' script is invoked if db connection details have changed.
        """
        old = SAMPLE_DB_UNIT_DATA.copy()
        assert old["host"] != "9.9.9.9"
        old["host"] = "9.9.9.9"
        update_persisted_data("db", old, hookenv=self.hookenv)
        self.hookenv.hook = "db-relation-changed"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])
