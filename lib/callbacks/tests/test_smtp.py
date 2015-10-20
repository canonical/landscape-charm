from charmhelpers.core.services.base import ServiceManager

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.callbacks.smtp import ConfigureSMTP
from lib.paths import DPKG_RECONFIGURE, DEBCONF_SET_SELECTIONS


class ConfigureSMTPTest(HookenvTest):

    def setUp(self):
        super(ConfigureSMTPTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.manager = ServiceManager([])
        self.callback = ConfigureSMTP(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run_with_relay_host(self):
        """
        If smtp-relay-host is set, postfix gets configured with a smarthost.
        """
        self.subprocess.add_fake_executable(DEBCONF_SET_SELECTIONS)
        self.subprocess.add_fake_executable(DPKG_RECONFIGURE)
        config = self.hookenv.config()
        config["smtp-relay-host"] = "my.smtp.server"
        self.callback(self.manager, "landscape", None)
        [process] = self.subprocess.processes
        self.assertIn("relayhost string my.smtp.server", process.input)
        self.assertIn(
            "main_mailer_type select Internet with smarthost", process.input)

    def test_run_without_relay_host(self):
        """
        If smtp-relay-host is not set, postfix gets configured as internet
        site.
        """
        self.subprocess.add_fake_executable(DEBCONF_SET_SELECTIONS)
        self.subprocess.add_fake_executable(DPKG_RECONFIGURE)
        config = self.hookenv.config()
        config["smtp-relay-host"] = ""
        self.callback(self.manager, "landscape", None)
        [process] = self.subprocess.processes
        self.assertIn("relayhost string ", process.input)
        self.assertIn("main_mailer_type select Internet Site", process.input)

    def test_run_no_change(self):
        """
        Nothing is done if the service had already been started and
        configuration hasn't changed.
        """
        self.manager.save_ready("landscape")
        config = self.hookenv.config()
        config["smtp-relay-host"] = "my.smtp.server"
        config.save()
        config.load_previous()
        self.callback(self.manager, "landscape", None)
        self.assertEqual([], self.subprocess.calls)
