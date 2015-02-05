from charmhelpers.core import templating

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import ClusterStub, HostStub
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA)
from lib.services import ServicesHook, SERVICE_CONF


class ServicesHookTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(ServicesHookTest, self).setUp()
        self.cluster = ClusterStub()
        self.host = HostStub()
        self.hook = ServicesHook(
            hookenv=self.hookenv, cluster=self.cluster, host=self.host)
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
            ("Incomplete relation: PostgreSQLRequirer", "DEBUG"),
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
                },
            }
        }
        self.hook()
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
        }
        [render] = self.renders
        self.assertEqual(
            ("service.conf", SERVICE_CONF, context, "landscape", "root", 416),
            render)

    def test_remote_leader_not_ready(self):
        """
        If we're not the leader unit and we didn't yet get relation data from
        the leader, we are not ready.
        """
        self.cluster.leader = False
        self.hook()
        self.assertIn(
            ("Incomplete relation: LandscapeRequirer", "DEBUG"),
            self.hookenv.messages)

    def test_remote_leader_ready(self):
        """
        If we're not the leader unit and we got relation data from the leader,
        along with the rest of required relations, then we're good.
        """
        self.cluster.leader = False
        self.hookenv.relations = {
            "cluster": {
                "cluster:1": {
                    "landscape/0": SAMPLE_LEADER_CONTEXT_DATA,
                },
            },
            "db": {
                "db:1": {
                    "postgresql/0": SAMPLE_DB_UNIT_DATA,
                },
            },
        }
        self.hook()
        self.assertEqual(1, len(self.renders))
