from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.pause import PauseAction
from lib.paths import LSCTL


class PauseActionTest(HookenvTest):

    def setUp(self):
        super(PauseActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(LSCTL)
        self.subprocess.add_fake_executable("service")
        self.action = PauseAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The PauseAction stops the Landscape services.
        """
        self.action()
        self.assertEqual(
            [(("/usr/bin/lsctl", "stop"), {})], self.subprocess.calls)

    def test_run_status(self):
        """
        The workload status is changed to 'maintenance' while stopping
        the services and after the services have been stopped.
        """
        self.action()
        self.assertEqual(
            ("maintenance", "Services stopped."), self.hookenv.status_get())
        self.assertEqual(
            [{"status": "unknown", "message": ""},
             {"status": "maintenance", "message": "Stopping services."},
             {"status": "maintenance", "message": "Services stopped."}],
            self.hookenv.statuses)
