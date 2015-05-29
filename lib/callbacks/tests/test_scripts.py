from fixtures import TestWithFixtures

from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.paths import LSCTL, SCHEMA_SCRIPT


class SchemaBootstrapTest(TestWithFixtures):

    def setUp(self):
        super(SchemaBootstrapTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.callback = SchemaBootstrap(subprocess=self.subprocess)

    def test_options(self):
        """
        The schema script is invoked with the --bootstrap option.
        """
        self.callback(None, None, None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap"],
            self.subprocess.calls[0][0])


class LSCtlTest(HookenvTest):

    def setUp(self):
        super(LSCtlTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(LSCTL)
        self.callback = LSCtl(subprocess=self.subprocess, hookenv=self.hookenv)

    def test_start(self):
        """
        The 'lsctl' script is invoked with the 'restart' action if the event
        name is 'start'.
        """
        self.callback(None, None, "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_stop(self):
        """
        The 'lsctl' script is invoked with the 'stop' action if the event name
        is 'stop'.
        """
        self.callback(None, None, "stop")
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
        self.callback(None, None, "start")
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
        self.callback(None, None, "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])
