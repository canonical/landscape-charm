from fixtures import TestWithFixtures, EnvironmentVariable, TempDir

from lib.tests.stubs import HookenvStub


class HookenvTest(TestWithFixtures):
    """A test providing a L{HookenvStub} for simulating a hook context."""

    def setUp(self):
        super(HookenvTest, self).setUp()
        # XXX The charmhelpers.core.hookenv.Config class grabs its path from
        #     the environment, so it's not very test-friendly. Should be fixed
        #     upstream.
        charm_dir = self.useFixture(TempDir())
        self.useFixture(EnvironmentVariable("CHARM_DIR", charm_dir.path))
        self.hookenv = HookenvStub()
