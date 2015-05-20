from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.resume import ResumeAction


class ResumeActionTest(HookenvTest):

    def setUp(self):
        super(ResumeActionTest, self).setUp()
        self.subprocess = SubprocessStub()
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
            [(("/usr/bin/lsctl", "start"), {}),
             (("service", "cron", "start"), {})],
            self.subprocess.calls)
