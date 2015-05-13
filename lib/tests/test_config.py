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
        The L{ConfigHook} re-configures APT sources if they have changed.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config.load_previous()
        config["source"] = "ppa:landscape/15.01"
        self.assertEqual(0, self.hook())
        self.assertTrue(len(self.fetch.sources) == 1)

    def test_save_after_change(self):
        """
        The L{ConfigHook} saves previous config values when called.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        self.assertIsNone(config.previous("source"))
        self.hook()
        config.load_previous()
        self.assertEqual("ppa:landscape/14.10", config.previous("source"))

        config["source"] = "ppa:landscape/15.01"
        self.hook()
        config.load_previous()
        self.assertEqual("ppa:landscape/15.01", config.previous("source"))
