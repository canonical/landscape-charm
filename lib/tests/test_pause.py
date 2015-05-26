from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.pause import PauseAction
from lib.paths import LSCTL


class PauseActionTest(HookenvTest):

    def setUp(self):
        super(PauseActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_call(LSCTL)
        self.subprocess.add_fake_call("service")
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
