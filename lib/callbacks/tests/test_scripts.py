from fixtures import EnvironmentVariable

from charmhelpers.core.services.base import ServiceManager

from lib.paths import LSCTL, SCHEMA_SCRIPT
from lib.callbacks.scripts import SchemaBootstrap, LSCtl, CONFIG_ONLY_FLAG
from lib.utils import update_persisted_data
from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.tests.sample import SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_DATA


class SchemaBootstrapTest(HookenvTest):

    with_hookenv_monkey_patching = True

    def setUp(self):
        super(SchemaBootstrapTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.manager = ServiceManager(services=[{"service": "landscape"}])
        self.callback = SchemaBootstrap(
            subprocess=self.subprocess, hookenv=self.hookenv)

    def test_options(self):
        """
        The schema script is invoked with the --bootstrap option and the proxy
        options.
        """
        self.callback(self.manager, "landscape", None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap"],
            self.subprocess.calls[1][0])

    def test_with_no_proxy_support_in_schema_script(self):
        """
        If there's no proxy support in the schema script, the relevant options
        are not passed.
        """
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"], stdout="Usage: --foo --bar")
        self.useFixture(EnvironmentVariable("http_proxy", "http://host:3128"))
        self.callback(self.manager, "landscape", None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap"],
            self.subprocess.calls[1][0])

    def test_with_proxy_settings(self):
        """
        The proxy options are set according to the environment variables.
        """
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"], stdout="Usage: --with-http-proxy")
        self.useFixture(EnvironmentVariable("http_proxy", "http://foo:3128"))
        self.useFixture(EnvironmentVariable("https_proxy", "http://bar:3128"))
        self.useFixture(EnvironmentVariable("no_proxy", "localhost"))
        self.callback(self.manager, "landscape", None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap",
             "--with-http-proxy", "http://foo:3128",
             "--with-https-proxy", "http://bar:3128",
             "--with-no-proxy", "localhost"],
            self.subprocess.calls[1][0])

    def test_was_ready(self):
        """
        If the services was ready, the schema bootstrap is not invoked again.
        """
        self.manager.save_ready("landscape")
        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (['/usr/bin/landscape-schema', '-h'], {})], self.subprocess.calls)

    def test_update_config(self):
        """Updating config are updated in Landscape."""
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"], stdout="Usage: " + CONFIG_ONLY_FLAG)

        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["root-url"] = "https://old.sad/"
        config.save()
        self.manager.save_ready("landscape")

        config["root-url"] = "https://happy.new/"
        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (["/usr/bin/landscape-schema", "-h"], {}),
            (["/usr/bin/landscape-schema", CONFIG_ONLY_FLAG, "--with-root-url",
              "https://happy.new/"], {}),
        ], self.subprocess.calls)

    def test_update_config_unsupported_flag(self):
        """Configuration is NOOP if the configure-lds flag is not supported."""
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"], stdout="Usage: --spam")

        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["root-url"] = "https://old.sad/"
        config.save()
        self.manager.save_ready("landscape")
        config["root-url"] = "https://happy.new/"

        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (["/usr/bin/landscape-schema", "-h"], {}),
        ], self.subprocess.calls)

    def test_bootstrap_and_configure(self):
        """Configuration is done after bootstrap, if config values exist."""
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"], stdout="Usage: " + CONFIG_ONLY_FLAG)

        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["system-email"] = "noreply@spam"
        config.save()
        config["system-email"] = "noreply@scape"

        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (["/usr/bin/landscape-schema", "-h"], {}),
            (["/usr/bin/landscape-schema", "--bootstrap"], {}),
            (["/usr/bin/landscape-schema", CONFIG_ONLY_FLAG,
              "--with-system-email", "noreply@scape"], {}),
        ], self.subprocess.calls)

    def test_inherit_model_proxy(self):
        """Proxy config is inherited from the model if unset on charm."""
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"],
            stdout="Usage: --with-http-proxy " + CONFIG_ONLY_FLAG)
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["http-proxy"] = "spam"
        config["https-proxy"] = "spam"
        config["no-proxy"] = "spam"
        config.save()
        del config["http-proxy"]
        del config["https-proxy"]
        del config["no-proxy"]
        self.useFixture(EnvironmentVariable("http_proxy", "http://foo:3128"))
        self.useFixture(EnvironmentVariable("https_proxy", "http://bar:3128"))
        self.useFixture(EnvironmentVariable("no_proxy", "localhost"))
        self.manager.save_ready("landscape")

        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (["/usr/bin/landscape-schema", "-h"], {}),
            (["/usr/bin/landscape-schema", CONFIG_ONLY_FLAG,
              "--with-http-proxy", "http://foo:3128",
              "--with-https-proxy", "http://bar:3128",
              "--with-no-proxy", "localhost"], {}),
        ], self.subprocess.calls)

    def test_change_model_proxy(self):
        """Proxy config override model proxy if configured on charm."""
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"],
            stdout="Usage: --with-http-proxy " + CONFIG_ONLY_FLAG)
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        self.useFixture(EnvironmentVariable("http_proxy", "spam"))
        self.useFixture(EnvironmentVariable("https_proxy", "spam"))
        self.useFixture(EnvironmentVariable("no_proxy", "spam"))
        self.manager.save_ready("landscape")
        config["http-proxy"] = "http://foo:3128"
        config["https-proxy"] = "http://bar:3128"
        config["no-proxy"] = "localhost"

        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (["/usr/bin/landscape-schema", "-h"], {}),
            (["/usr/bin/landscape-schema", CONFIG_ONLY_FLAG,
              "--with-http-proxy", "http://foo:3128",
              "--with-https-proxy", "http://bar:3128",
              "--with-no-proxy", "localhost"], {}),
        ], self.subprocess.calls)

    def test_unset_model_proxy(self):
        """Proxy config can explicitly unset model proxy."""
        self.subprocess.add_fake_executable(
            SCHEMA_SCRIPT, args=["-h"],
            stdout="Usage: --with-http-proxy " + CONFIG_ONLY_FLAG)
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        self.useFixture(EnvironmentVariable("http_proxy", "spam"))
        self.useFixture(EnvironmentVariable("https_proxy", "spam"))
        self.useFixture(EnvironmentVariable("no_proxy", "spam"))
        self.manager.save_ready("landscape")
        config["http-proxy"] = ""
        config["https-proxy"] = ""
        config["no-proxy"] = ""

        self.callback(self.manager, "landscape", None)
        self.assertEqual([
            (["/usr/bin/landscape-schema", "-h"], {}),
            (["/usr/bin/landscape-schema", CONFIG_ONLY_FLAG,
              "--with-http-proxy", "",
              "--with-https-proxy", "",
              "--with-no-proxy", ""], {}),
        ], self.subprocess.calls)

    def test_reconfigure_noop(self):
        """Nothing happens if there is no proxy and no config change."""
        # TODO


class LSCtlTest(HookenvTest):

    with_hookenv_monkey_patching = True

    def setUp(self):
        super(LSCtlTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(LSCTL)
        self.services = [{
            "service": "landscape",
            "required_data": [
                {"db": [SAMPLE_DB_UNIT_DATA]},
                {"leader": SAMPLE_LEADER_DATA},
            ]
        }]
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

    def test_start_unknown_status(self):
        """
        If the 'lsctl' script is invoked with the 'restart' action when
        the workload status is 'unknown', the status while restarting
        the services will way 'starting services' and the final status
        will be 'active'.
        """
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(("active", ""), self.hookenv.status_get())
        self.assertEqual(
            [{"status": "unknown", "message": ""},
             {"status": "maintenance", "message": "Starting services."},
             {"status": "active", "message": ""}],
            self.hookenv.statuses)

    def test_start_active_status(self):
        """
        If the 'lsctl' script is invoked with the 'restart' action when
        the workload status is 'active', the status while restarting
        the services will way 'restarting services' and the final status
        will be 'active' with no status message.
        """
        self.hookenv.statuses = [{"status": "active", "message": "Something."}]
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(("active", ""), self.hookenv.status_get())
        self.assertEqual(
            [{"status": "active", "message": "Something."},
             {"status": "maintenance", "message": "Restarting services."},
             {"status": "active", "message": ""}],
            self.hookenv.statuses)

    def test_start_maintenance_status(self):
        """
        If the 'lsctl' script is invoked with the 'restart' action when
        the workload status is 'maintenance', the services won't be
        restarted and the workload status won't be changed.
        """
        self.hookenv.statuses = [
            {"status": "maintenance", "message": "Doing maintenance."}]
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ("maintenance", "Doing maintenance."), self.hookenv.status_get())
        self.assertEqual(
            [{"status": "maintenance", "message": "Doing maintenance."}],
            self.hookenv.statuses)
        self.assertEqual([], self.subprocess.calls)

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

    def test_config_changed_only_smtp(self):
        """
        The 'lsctl' script is not invoked if only the SMTP relay host changed.
        """
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config["smtp-relay-host"] = "mx.first"
        config.save()
        config["smtp-relay-host"] = "mx.second"
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
        # update sample data
        rel_data = {}
        for item in old["master"].split(' '):
            key, value = item.split('=')
            if key == 'host':
                assert value != "9.9.9.9"
                rel_data[key] = "9.9.9.9"
            else:
                rel_data[key] = value
        old["master"] = " ".join("{}={}".format(k, v)
                                 for k, v in rel_data.items())
        assert old["host"] != "9.9.9.9"
        old["host"] = "9.9.9.9"
        update_persisted_data("db", old, hookenv=self.hookenv)
        self.hookenv.hook = "db-relation-changed"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_leader_elected(self):
        """
        The 'lsctl' script is invoked if leader details have changed, for
        example if a non-leader unit becomes the leader.
        """
        old = SAMPLE_LEADER_DATA.copy()
        old["is_leader"] = False
        update_persisted_data("leader", old, hookenv=self.hookenv)
        self.hookenv.hook = "leader-settings-changed"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_leader_deposed(self):
        """
        The 'lsctl' script is not invoked if leader details have changed
        because the unit was the leader but got deposed.
        """
        old = SAMPLE_LEADER_DATA.copy()
        old["is_leader"] = True
        update_persisted_data("leader", old, hookenv=self.hookenv)
        self.hookenv.leader = False
        self.hookenv.hook = "leader-settings-changed"
        self.callback(self.manager, "landscape", "start")
        self.assertEqual([], self.subprocess.calls)
