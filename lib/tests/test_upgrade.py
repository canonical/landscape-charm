from lib.tests.helpers import HookenvTest
from lib.tests.stubs import FetchStub
from lib.upgrade import UpgradeAction


class UpgradeActionTest(HookenvTest):

    def setUp(self):
        super(UpgradeActionTest, self).setUp()
        self.fetch = FetchStub()
        self.action = UpgradeAction(
            hookenv=self.hookenv, fetch=self.fetch)

    def test_run(self):
        """
        The UpgradeAction refreshes package indexes and upgrades
        landscape-server package.
        """
        self.action()
        # There was on non-fatal apt_update call.
        self.assertEqual([True], self.fetch.updates)
        # And one apt_install with appropriate options.
        self.assertEqual(
            [(("landscape-server",),
              ["-o", 'Dpkg::Options::="--force-confdef"',
               "-o", 'Dpkg::Options::="--force-confold"'],
              True)], self.fetch.installed)
