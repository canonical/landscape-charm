import os

from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir
from lib.tests.stubs import SubprocessStub
from lib.resume import ResumeAction
from lib.paths import LSCTL


class ResumeActionTest(HookenvTest):

    def setUp(self):
        super(ResumeActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(LSCTL, args=["start"])
        self.subprocess.add_fake_executable(LSCTL, args=["status"])
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths

    def test_run(self):
        """
        The ResumeAction starts the Landscape services, including
        enabling the cron service so that Landscape cron jobs can start
        running again.
        """
        open(self.paths.maintenance_flag(), "w")
        self.addCleanup(os.remove, self.paths.maintenance_flag())

        action = ResumeAction(
            hookenv=self.hookenv, subprocess=self.subprocess, paths=self.paths)
        action()
        self.assertEqual(
            [(("/usr/bin/lsctl", "start"), {}),
             (("/usr/bin/lsctl", "status"), {})],
            self.subprocess.calls)

    def test_run_without_maintenance_flag(self):
        """
        When no maintenance flag file is present, resume action is a no-op.
        """
        action = ResumeAction(
            hookenv=self.hookenv, subprocess=self.subprocess, paths=self.paths)
        action()
        self.assertEqual([], self.subprocess.calls)

    def test_run_fail(self):
        """
        """
        open(self.paths.maintenance_flag(), "w")
        self.addCleanup(os.remove, self.paths.maintenance_flag())
        self.subprocess.add_fake_executable(
            LSCTL, args=["start"], stdout="start output")
        self.subprocess.add_fake_executable(
            LSCTL, args=["status"], stdout="status failure", return_code=3)
        self.subprocess.add_fake_executable(LSCTL, args=["stop"])

        action = ResumeAction(
            hookenv=self.hookenv, subprocess=self.subprocess, paths=self.paths)
        action()
        self.assertEqual(
            ["Some services failed to start.\n\nstart output\n\n"
             "status failure"],
            self.hookenv.action_fails)
        self.assertEqual(
            [(("/usr/bin/lsctl", "start"), {}),
             (("/usr/bin/lsctl", "status"), {}),
             (("/usr/bin/lsctl", "stop"), {})],
            self.subprocess.calls)
