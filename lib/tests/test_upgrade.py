from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.upgrade import UpgradeAction
from lib.apit import INSTALL_PACKAGES


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
        self.hookenv.status_set("maintenance", "")

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
            [(INSTALL_PACKAGES,
              ["--option=Dpkg::Options::=--force-confdef",
               "--option=Dpkg::Options::=--force-confold"],
              True)], self.fetch.installed)

    def test_run_without_maintenance_flag(self):
        """
        If the unit is not in the 'maintenance' state, the upgrade
        action is a no-op.
        """
        self.hookenv.status_set("active", "")

        action = UpgradeAction(
            hookenv=self.hookenv, fetch=self.fetch, paths=self.paths,
            subprocess=self.subprocess)

        action()
        # There were no apt_update calls or apt_install calls.
        self.assertEqual([], self.fetch.updates)
        self.assertEqual([], self.fetch.installed)

    def test_upgrade_holds_packages(self):
        """
        The upgrade action holds the landscape packages.
        """
        self.hookenv.status_set("maintenance", "")
        self.hookenv.config()["source"] = "ppa:my-ppa"

        action = UpgradeAction(
            hookenv=self.hookenv, fetch=self.fetch, paths=self.paths,
            subprocess=self.subprocess)
        action()

        unhold_call = [
            "apt-mark", "unhold", "landscape-server", "landscape-hashids"]
        hold_call = [
            "apt-mark", "hold", "landscape-server", "landscape-hashids"]
        self.assertEqual(unhold_call, self.subprocess.calls[0][0])
        self.assertEqual(hold_call, self.subprocess.calls[1][0])
