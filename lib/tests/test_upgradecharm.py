from lib.tests.helpers import HookenvTest
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.upgradecharm import UpgradeCharmHook


class UpgradeCharmHookTest(HookenvTest):

    def setUp(self):
        super(UpgradeCharmHookTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.hook = UpgradeCharmHook(
            hookenv=self.hookenv, fetch=self.fetch, subprocess=self.subprocess)

    def test_run(self):
        """
        The L{UpgradeCharmHook} configures APT sources and install the needed
        packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.assertEqual(0, self.hook())
        self.assertNotEqual([], self.fetch.sources)
        self.assertNotEqual([], self.fetch.installed)
