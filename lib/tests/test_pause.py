from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.pause import PauseAction


class PauseActionTest(HookenvTest):

    def setUp(self):
        super(PauseActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.action = PauseAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The PauseAction stops the Landscape services.
        """
        self.action()
        self.assertEqual(
            [(("/usr/bin/lsctl", "stop"), {}),
             (("service", "cron", "stop"), {})],
            self.subprocess.calls)
