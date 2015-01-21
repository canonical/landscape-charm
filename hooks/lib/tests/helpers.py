from fixtures import Fixture, TestWithFixtures, EnvironmentVariable, TempDir
from charmhelpers.core.hookenv import Config


class LoggerFixture(Fixture):
    """Provide a testable stub for C{charmhelpers.hookenv.log}."""

    def setUp(self):
        super(LoggerFixture, self).setUp()
        self.messages = []

    def log(self, message, level=None):
        self.messages.append((message, level))


class ConfigFixture(Fixture):
    """Provide a testable stub for C{charmhelpers.hookenv.config}."""

    def setUp(self):
        super(ConfigFixture, self).setUp()
        # XXX The charmhelpers.core.hookenv.Config class grabs its path from
        #     the environment, so it's not very test-friendly. Should be fixed
        #     upstream.
        charm_dir = self.useFixture(TempDir())
        self.useFixture(EnvironmentVariable("CHARM_DIR", charm_dir.path))
        self.data = Config()

    def config(self):
        return self.data


class HookTest(TestWithFixtures):

    def setUp(self):
        super(HookTest, self).setUp()
        self.logger = self.useFixture(LoggerFixture())
        self.config = self.useFixture(ConfigFixture())
