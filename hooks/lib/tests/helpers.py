import os

from jinja2 import FileSystemLoader, Environment

from fixtures import TestWithFixtures, EnvironmentVariable, TempDir

from charmhelpers.core import hookenv

from lib.tests.stubs import HookenvStub


class HookenvTest(TestWithFixtures):
    """A test providing a L{HookenvStub} for simulating a hook context.

    @ivar with_hookenv_monkey_patch: If C{True} the real hookenv module from
       charmhelpers will be monkey patched and replaced with the local stub
       instance from this test.
    """

    with_hookenv_monkey_patch = False

    def setUp(self):
        super(HookenvTest, self).setUp()
        # XXX The charmhelpers.core.hookenv.Config class grabs its path from
        #     the environment, so it's not very test-friendly. Should be fixed
        #     upstream.
        charm_dir = self.useFixture(TempDir())
        self.useFixture(EnvironmentVariable("CHARM_DIR", charm_dir.path))
        self.hookenv = HookenvStub(charm_dir.path)

        if self.with_hookenv_monkey_patch:
            self._monkey_patch_hookenv()

    def _monkey_patch_hookenv(self):
        """Monkey patch C{charmhelpers.core.hookenv} module making it testable.

        XXX Since charmhelpers doesn't use dependency injection, we need to
            monkey patch the real hookenv API and just have it behave like an
            injected L{HookenvStub}.
        """
        for name in dir(self.hookenv):
            attribute = getattr(self.hookenv, name)
            if name.startswith("_") or not callable(attribute):
                continue
            self.addCleanup(setattr, hookenv, name, getattr(hookenv, name))
            setattr(hookenv, name, attribute)


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
