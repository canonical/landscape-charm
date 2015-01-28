import os

from jinja2 import FileSystemLoader, Environment

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


class TemplateTest(TestWithFixtures):
    """A test for rendering templates."""

    template_filename = None  # MUST be set be subclasses

    def setUp(self):
        super(TestWithFixtures, self).setUp()
        charm_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        templates_dir = os.path.join(charm_dir, "templates")
        loader = Environment(loader=FileSystemLoader(templates_dir))
        self.template = loader.get_template(self.template_filename)
