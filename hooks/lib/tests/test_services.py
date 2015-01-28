from charmhelpers.core import hookenv

from lib.tests.helpers import HookenvTest
from lib.services import ServicesHook


class ServicesHookTest(HookenvTest):

    def setUp(self):
        super(ServicesHookTest, self).setUp()
        self.hook = ServicesHook(hookenv=self.hookenv)
        self.addCleanup(setattr, hookenv, "relation_ids", hookenv.relation_ids)
        self.addCleanup(setattr, hookenv, "log", hookenv.log)
        self.addCleanup(setattr, hookenv, "config", hookenv.log)
        hookenv.relation_ids = self.hookenv.relation_ids
        hookenv.log = self.hookenv.log
        hookenv.config = self.hookenv.config

    def test_db_relation_not_ready(self):
        """
        If the db relation doesn't provide the required keys, the services hook
        """
        self.hook()
        self.assertIn(
            ("Incomplete relation: PostgreSQLRelation", "DEBUG"),
            self.hookenv.messages)

    def test_db_relation_ready(self):
        """
        If the db relation doesn't provide the required keys, the services hook
        """
        self.hookenv.relations = {
            "db": ["db"]
        }
        self.hook()
        self.assertIn(
            ("Incomplete relation: PostgreSQLRelation", "DEBUG"),
            self.hookenv.messages)
