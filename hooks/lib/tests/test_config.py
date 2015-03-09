from lib.tests.helpers import HookenvTest
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.config import ConfigHook


class ConfigHookTest(HookenvTest):

    def setUp(self):
        super(ConfigHookTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.hook = ConfigHook(
            hookenv=self.hookenv, fetch=self.fetch, subprocess=self.subprocess)

    def test_run(self):
        """
        The L{ConfigHook} re-configures APT sources if the have changed.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config.load_previous()
        config["source"] = "ppa:landscape/15.01"
        self.assertEqual(0, self.hook())
        self.assertTrue(len(self.fetch.sources) > 0)
