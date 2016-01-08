import os

from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.upgrade import UpgradeAction


class UpgradeActionTest(HookenvTest):

    def setUp(self):
        super(UpgradeActionTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable("apt-mark")
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths

    def test_run(self):
        """
        The UpgradeAction refreshes package indexes and upgrades
        landscape-server package.
        """

        open(self.paths.maintenance_flag(), "w")
        self.addCleanup(os.remove, self.paths.maintenance_flag())

        self.hookenv.config()["source"] = "ppa:my-ppa"
        action = UpgradeAction(
            hookenv=self.hookenv, fetch=self.fetch, paths=self.paths,
            subprocess=self.subprocess)
        action()

        self.assertEqual([("ppa:my-ppa", None)], self.fetch.sources)

        # There was fatal apt_update call.
        self.assertEqual([True], self.fetch.updates)
        # And one apt_install with appropriate options.
        self.assertEqual(
            [(("landscape-server", "landscape-hashids", "python-psutil"),
              ["--option=Dpkg::Options::=--force-confdef",
               "--option=Dpkg::Options::=--force-confold",
               "--ignore-hold"],
              True)], self.fetch.installed)

    def test_run_without_maintenance_flag(self):
        """
        When maintenance flag file is absent, upgrade action is a no-op.
        """

        action = UpgradeAction(
            hookenv=self.hookenv, fetch=self.fetch, paths=self.paths,
            subprocess=self.subprocess)

        action()
        # There were no apt_update calls or apt_install calls.
        self.assertEqual([], self.fetch.updates)
        self.assertEqual([], self.fetch.installed)
