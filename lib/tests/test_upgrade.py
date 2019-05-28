from charmhelpers.core import hookenv

from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.upgrade import UpgradeAction
from lib.apt import INSTALL_PACKAGES


class UpgradeActionTest(HookenvTest):

    def setUp(self):
        super(UpgradeActionTest, self).setUp()
        self.fetch = FetchStub(self.hookenv.config)
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
            "apt-mark", "unhold", "landscape-server", "landscape-hashids",
            "landscape-api"]
        hold_call = [
            "apt-mark", "hold", "landscape-server", "landscape-hashids",
            "landscape-api"]
        self.assertEqual(unhold_call, self.subprocess.calls[0][0])
        self.assertEqual(hold_call, self.subprocess.calls[1][0])

    def test_run_logging(self):
        """Make sure that logging for the action happens correctly."""
        self.subprocess.add_fake_executable('apt-mark',
                                            ['unhold', 'landscape-server',
                                             'landscape-hashids'])
        self.subprocess.add_fake_executable('apt-mark',
                                            ['hold', 'landscape-server',
                                             'landscape-hashids'])
        self.hookenv.status_set("maintenance", "")
        self.hookenv.config()["source"] = "ppa:my-ppa"
        action = UpgradeAction(hookenv=self.hookenv, fetch=self.fetch,
                               paths=self.paths, subprocess=self.subprocess)

        action()

        self.assertEqual(self.hookenv.messages,
                         [('Running action UpgradeAction', None),
                          ('Adding repository: ppa:my-ppa', None),
                          ('running \'apt-mark unhold landscape-server '
                           'landscape-hashids landscape-api\'',
                           hookenv.DEBUG),
                          ('running \'apt-mark hold landscape-server '
                           'landscape-hashids landscape-api\'',
                           hookenv.DEBUG),
                          ])

    def test_run_failure(self):
        """Make sure the upgrade action handles failures correctly.

        This entails logging and setting the failure in the hook env.
        """
        self.subprocess.add_fake_executable('apt-mark',
                                            ['unhold', 'landscape-server',
                                             'landscape-hashids',
                                             'landscape-api'],
                                            return_code=1)
        self.hookenv.status_set("maintenance", "")
        self.hookenv.config()["source"] = "ppa:my-ppa"
        action = UpgradeAction(hookenv=self.hookenv, fetch=self.fetch,
                               paths=self.paths, subprocess=self.subprocess)

        action()

        self.assertEqual(self.hookenv.messages,
                         [('Running action UpgradeAction', None),
                          ('Adding repository: ppa:my-ppa', None),
                          ('running \'apt-mark unhold landscape-server '
                           'landscape-hashids landscape-api\'',
                           hookenv.DEBUG),
                          ('got return code 1 running \'apt-mark unhold '
                           'landscape-server landscape-hashids '
                           'landscape-api\'',
                           hookenv.ERROR),
                          ])
        self.assertEqual(self.hookenv.action_fails,
                         ['command failed (see unit logs): apt-mark unhold '
                          'landscape-server landscape-hashids landscape-api'])
