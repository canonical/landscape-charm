from fixtures import TestWithFixtures

from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.tests.stubs import SubprocessStub


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
        The 'lsct' script is invoked with the 'restart' action if the event
        name is 'start'.
        """
        self.callback(None, None, "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])

    def test_stop(self):
        """
        The 'lsct' script is invoked with the 'stop' action if the event name
        is 'stop'.
        """
        self.callback(None, None, "stop")
        self.assertEqual(
            ["/usr/bin/lsctl", "stop"], self.subprocess.calls[0][0])
