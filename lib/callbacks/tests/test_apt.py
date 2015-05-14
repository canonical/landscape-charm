from lib.tests.helpers import HookenvTest
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.callbacks.apt import SetAPTSources


class SetAPTSourcesTest(HookenvTest):

    def setUp(self):
        super(SetAPTSourcesTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.callback = SetAPTSources(
            hookenv=self.hookenv, fetch=self.fetch, subprocess=self.subprocess)

    def test_run(self):
        """
        The SetAPTSources callback re-configures APT sources if they have
        changed.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config["source"] = "ppa:landscape/15.01"
        self.callback(None, None, None)
        self.assertEqual(1, len(self.fetch.sources), repr(self.fetch.sources))
