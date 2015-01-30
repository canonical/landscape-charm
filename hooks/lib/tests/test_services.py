from charmhelpers.core import templating

from lib.tests.helpers import HookenvTest
from lib.tests.sample import SAMPLE_DB_UNIT_DATA
from lib.services import ServicesHook, SERVICE_CONF


class ServicesHookTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(ServicesHookTest, self).setUp()
        self.hook = ServicesHook(hookenv=self.hookenv)
        self.renders = []

        # XXX Monkey patch the templating API, charmhelpers doesn't sport
        #     any dependency injection here as well.
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
                    "postgresql/0": SAMPLE_DB_UNIT_DATA,
                }
            }
        }
        self.hook()
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
        }
        [render] = self.renders
        self.assertEqual(
            ("service.conf", SERVICE_CONF, context, "landscape", "root", 416),
            render)
