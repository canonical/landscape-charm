from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.upgrade import UpgradeAction


class UpgradeActionTest(HookenvTest):

    def setUp(self):
        super(UpgradeActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.action = UpgradeAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The UpgradeAction refreshes package indexes and upgrades
        landscape-server package.
        """
        self.action()
        self.assertEqual(
            [(("apt-get", "update", "-y"), {}),
             (["apt-get", "install", "-y",
               "-o", 'Dpkg::Options::="--force-confdef"',
               "-o", 'Dpkg::Options::="--force-confold"',
               "landscape-server"], {})],
            self.subprocess.calls)
