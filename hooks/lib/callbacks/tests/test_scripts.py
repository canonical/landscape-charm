from fixtures import TestWithFixtures

from charmhelpers.core.services.base import ServiceManager

from lib.callbacks.scripts import EnsureConfigDir, SchemaBootstrap, LSCtl
from lib.tests.stubs import SubprocessStub
from lib.tests.helpers import HookenvTest


class EnsureConfigDirTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(EnsureConfigDirTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.callback = EnsureConfigDir(subprocess=self.subprocess)

    def test_options(self):
        """
        The callback invokes a shell command to create a config dir symlink
        if needed.
        """
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [{"hosted": [{"deployment-mode": "edge"}]}],
        }])
        self.callback(manager, "landscape", None)
        self.assertEqual(
            ["/bin/sh", "-c",
             "if ! [ -e /opt/canonical/landscape/configs/edge ]; " +
             "then ln -s /opt/canonical/landscape/configs/standalone " +
             "/opt/canonical/landscape/configs/edge; fi"],
            self.subprocess.calls[0][0])


class SchemaBootstrapTest(TestWithFixtures):

    def setUp(self):
        super(SchemaBootstrapTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.callback = SchemaBootstrap(subprocess=self.subprocess)

    def test_options(self):
        """
        The schema script is invoked with the --bootstrap option.
        """
        self.callback(None, None, None)
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap"],
            self.subprocess.calls[0][0])


class LSCtlTest(TestWithFixtures):

    def setUp(self):
        super(LSCtlTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.callback = LSCtl(subprocess=self.subprocess)

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
