from charmhelpers.core import hookenv
from charmhelpers.core import templating

from lib.tests.helpers import HookenvTest
from lib.tests.sample import SAMPLE_POSTGRESQL_RELATION_DATA
from lib.services import ServicesHook, SERVICE_CONF


class ServicesHookTest(HookenvTest):

    def setUp(self):
        super(ServicesHookTest, self).setUp()
        self.hook = ServicesHook(hookenv=self.hookenv)

        # XXX Since charmhelpers doesn't use dependency injection, we need
        # to monkey patch the real hookenv API and just have it behave like an
        # injected HookenvStub.
        for name in dir(self.hookenv):
            attribute = getattr(self.hookenv, name)
            if name.startswith("_") or not callable(attribute):
                continue
            self.addCleanup(setattr, hookenv, name, getattr(hookenv, name))
            setattr(hookenv, name, attribute)
        self.renders = []

        # XXX Same for the templating API.
        self.addCleanup(setattr, templating, "render", templating.render)
        templating.render = lambda *args: self.renders.append(args)

    def test_db_relation_not_ready(self):
        """
        If the db relation doesn't provide the required keys, the services hook
        doesn't try to change any configuration.
        """
        self.hook()
        self.assertIn(
            ("Incomplete relation: PostgreSQLRelation", "DEBUG"),
            self.hookenv.messages)

    def test_db_relation_ready(self):
        """
        If the db relation provides the required keys, the services hook
        rewrites the service configuration.
        """
        self.hookenv.relations = {
            "db": {
                "db:1": {
                    "postgresql/0": SAMPLE_POSTGRESQL_RELATION_DATA,
                }
            }
        }
        self.hook()
        context = {
            "db": [SAMPLE_POSTGRESQL_RELATION_DATA],
        }
        [render] = self.renders
        self.assertEqual(
            ("service.conf", SERVICE_CONF, context, "landscape", "root", 416),
            render)
