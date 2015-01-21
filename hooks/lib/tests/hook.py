from fixtures import TestWithFixtures, EnvironmentVariable, TempDir

from lib.tests.stubs import HookenvStub


class HookTest(TestWithFixtures):
    """Helper for testes exercising L{Hook}-based classes."""

    def setUp(self):
        super(HookTest, self).setUp()
        # XXX The charmhelpers.core.hookenv.Config class grabs its path from
        #     the environment, so it's not very test-friendly. Should be fixed
        #     upstream.
        charm_dir = self.useFixture(TempDir())
        self.useFixture(EnvironmentVariable("CHARM_DIR", charm_dir.path))
        self.hookenv = HookenvStub()
