from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.resume import ResumeAction
from lib.paths import LSCTL


class ResumeActionTest(HookenvTest):

    def setUp(self):
        super(ResumeActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(LSCTL)
        self.subprocess.add_fake_executable("service")
        self.action = ResumeAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The ResumeAction starts the Landscape services, including
        enabling the cron service so that Landscape cron jobs can start
        running again.
        """
        self.action()
        self.assertEqual(
            [(("/usr/bin/lsctl", "start"), {})], self.subprocess.calls)
