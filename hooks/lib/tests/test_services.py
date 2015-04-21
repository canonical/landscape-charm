import os

from fixtures import TempDir

from charmhelpers.core import templating

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import ClusterStub, HostStub, SubprocessStub
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA, SAMPLE_AMQP_UNIT_DATA,
    SAMPLE_CONFIG_OPENID_DATA, SAMPLE_HOSTED_DATA, SAMPLE_WEBSITE_UNIT_DATA)
from lib.services import ServicesHook, SERVICE_CONF, DEFAULT_FILE
from lib.tests.offline_fixture import OfflineDir


class ServicesHookTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(ServicesHookTest, self).setUp()
        self.cluster = ClusterStub()
        self.host = HostStub()
        self.subprocess = SubprocessStub()
        self.offline_dir = self.useFixture(OfflineDir())
        self.configs_dir = self.useFixture(TempDir())
        self.ssl_certs_dir = self.useFixture(TempDir())
        self.hook = ServicesHook(
            hookenv=self.hookenv, cluster=self.cluster, host=self.host,
            subprocess=self.subprocess, offline_dir=self.offline_dir.path,
            configs_dir=self.configs_dir.path,
            ssl_certs_dir=self.ssl_certs_dir.path)

        # XXX Monkey patch the templating API, charmhelpers doesn't sport
        #     any dependency injection here as well.
        self.renders = []
        self.addCleanup(setattr, templating, "render", templating.render)
        templating.render = lambda *args: self.renders.append(args)

        # Setup sample relation data for the "common" happy case (an LDS
        # deployment with postgresql, haproxy and rabbitmq-server).
        self.hookenv.relations = {
            "db": {
                "db:1": {
                    "postgresql/0": SAMPLE_DB_UNIT_DATA.copy(),
                },
            },
            "amqp": {
                "amqp:1": {
                    "rabbitmq-server/0": SAMPLE_AMQP_UNIT_DATA.copy(),
                },
            },
            "website": {
                "website:1": {
                    "haproxy/0": SAMPLE_WEBSITE_UNIT_DATA.copy(),
                },
            },
        }

    def test_db_relation_not_ready(self):
        """
        If the db relation doesn't provide the required keys, the services hook
        doesn't try to change any configuration.
        """
        self.hookenv.relations.clear()

    def test_website_relation_provide(self):
        """
        If we're running the website-relation-joined hook, the HAProxyProvider
        is run and the remote relation is set accordingly.
        """
        self.hookenv.hook = "website-relation-joined"
        self.hook()
        # Assert that the HAProxyProvider has run by checking that it set the
        # relation with the dict returned by HAProxyProvider.provide_data (the
        # only key of that dict is 'services'). The ID of relation being set
        # is None because we're running in the website-relation-joined hook
        # and are using the default relation ID (which in a real-world
        # relation-set run will resolve to the relation for the http
        # interface).
        self.assertIn("services", self.hookenv.relations[None])

    def test_amqp_relation_not_ready(self):
        """
        If the amqp relation doesn't provide the required keys, the services
        hook doesn't try to change any configuration.
        """
        self.hookenv.relations.pop("amqp")
        self.hook()
        self.assertIn(
            ("Incomplete relation: RabbitMQRequirer", "DEBUG"),
            self.hookenv.messages)

    def test_ready(self):
        """
        If all dependency managers are ready, the services hook bootstraps the
        schema and rewrites the service configuration.
        """
        self.hook()
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "website": [SAMPLE_WEBSITE_UNIT_DATA],
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {},
            "is_leader": True,
        }

        self.assertEqual(
            ("service.conf", SERVICE_CONF, context, "landscape", "root", 416),
            self.renders[0])
        self.assertEqual(
            ("landscape-server", DEFAULT_FILE, context,
             "landscape", "root", 416),
            self.renders[1])
        [call1, call2] = self.subprocess.calls
        self.assertEqual(
            ["/usr/bin/landscape-schema", "--bootstrap"], call1[0])
        self.assertEqual(
            ["/usr/bin/lsctl", "restart"], call2[0])

    def test_ready_with_non_standalone_deployment_mode(self):
        """
        If deployment-mode is set to 'edge' an appropriate config symlink will
        be created
        """
        hosted_data = SAMPLE_HOSTED_DATA.copy()
        hosted_data["deployment-mode"] = "edge"
        self.hookenv.relations.update({
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/0": hosted_data,
                },
            },
        })
        self.hook()
        self.assertIsNotNone(os.lstat(self.configs_dir.join("edge")))

    def test_ready_write_ssl_cert(self):
        """
        When the data is ready the custom SSL certificate data gets
        written on disk.
        """
        self.hook()
        self.assertTrue(
            os.path.exists(self.ssl_certs_dir.join("landscape_server_ca.crt")))

    def test_ready_with_openid_configuration(self):
        """
        OpenID configuration is passed in to service.conf generation if
        it is set in the hook configuration.
        """
        self.hookenv.config().update(SAMPLE_CONFIG_OPENID_DATA)
        self.hook()
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "website": [SAMPLE_WEBSITE_UNIT_DATA],
            "config": SAMPLE_CONFIG_OPENID_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "is_leader": True,
        }

        self.assertEqual(
            ("service.conf", SERVICE_CONF, context, "landscape", "root", 416),
            self.renders[0])

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
        self.hookenv.relations.update({
            "cluster": {
                "cluster:1": {
                    "landscape/0": SAMPLE_LEADER_CONTEXT_DATA,
                },
            },
        })
        self.hook()
        self.assertEqual(2, len(self.renders))
