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
        The schema script is invoked with the LANDSCAPE_CONFIG environment
        variable set to 'standalone'.
        """
        self.callback(None, None, "start")
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], self.subprocess.calls[0][0])
