import os
import base64
import yaml

from charmhelpers.core import templating

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import HostStub, PsutilStub, SubprocessStub, FetchStub
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_DATA, SAMPLE_AMQP_UNIT_DATA,
    SAMPLE_CONFIG_LICENSE_DATA, SAMPLE_CONFIG_OPENID_DATA,
    SAMPLE_CONFIG_OIDC_DATA, SAMPLE_HOSTED_DATA, SAMPLE_WORKER_COUNT_DATA,
    SAMPLE_WEBSITE_UNIT_DATA, SAMPLE_CONFIG)
from lib.services import ServicesHook
from lib.tests.rootdir import RootDir
from lib.paths import (
    SCHEMA_SCRIPT, LSCTL, DPKG_RECONFIGURE, DEBCONF_SET_SELECTIONS)


class ServicesHookTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(ServicesHookTest, self).setUp()
        self.host = HostStub()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.subprocess.add_fake_executable(LSCTL)
        self.subprocess.add_fake_executable(DEBCONF_SET_SELECTIONS)
        self.subprocess.add_fake_executable(DPKG_RECONFIGURE)
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths
        self.root_dir = self.useFixture(RootDir())
        self.fetch = FetchStub(self.hookenv.config)
        self.psutil = PsutilStub(num_cpus=2, physical_memory=1*1024**3)
        self.hook = ServicesHook(
            hookenv=self.hookenv, host=self.host, subprocess=self.subprocess,
            paths=self.paths, fetch=self.fetch, psutil=self.psutil)

        # XXX Monkey patch the templating API, charmhelpers doesn't sport
        #     any dependency injection here as well.
        self.renders = []
        self.addCleanup(setattr, templating, "render", templating.render)
        templating.render = lambda *args, **kwargs: self.renders.append(args)

        # Setup sample data for the "common" happy case (an LDS
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
        self.hookenv.config().update(SAMPLE_CONFIG)

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
        # only key of that dict is 'services').
        self.assertIn("services", self.hookenv.relations["website:1"])

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
        config_expected = SAMPLE_CONFIG.copy()
        config_expected["worker-counts"] = {
            "appserver": 2, "message-server": 2, "pingserver": 2}

        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "leader": SAMPLE_LEADER_DATA,
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "website": [SAMPLE_WEBSITE_UNIT_DATA],
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": config_expected,
            "is_leader": True,
        }
        for render in self.renders:
            rendered_context = render[2]
            for key in context.keys():
                if key == 'db':
                    # check that all keys are in the rendered_context
                    expected = sorted(
                        ['master', 'host', 'port', 'user', 'password',
                         'database', 'allowed-units'])
                    self.assertEqual(expected,
                                     sorted(rendered_context[key][0].keys()))
                else:
                    self.assertEqual(context[key], rendered_context[key])

        self.assertEqual(
            ("service.conf", self.paths.service_conf()),
            self.renders[0][:2])
        self.assertEqual(
            ("landscape-server", self.paths.default_file()),
            self.renders[1][:2])

        calls = self.subprocess.calls
        executables = [call[0][0] for call in calls]
        self.assertEqual("/usr/bin/landscape-schema", executables[1])
        self.assertEqual("/usr/bin/debconf-set-selections", executables[2])
        self.assertEqual("/usr/sbin/dpkg-reconfigure", executables[3])
        self.assertEqual("/usr/bin/lsctl", executables[4])

        self.assertEqual(["/usr/bin/landscape-schema", "-h"], calls[0][0])

    def test_ready_with_non_standalone_deployment_mode(self):
        """
        If deployment-mode is set to 'edge' an appropriate config symlink will
        be created.
        """
        hosted_data = SAMPLE_HOSTED_DATA.copy()
        hosted_data["deployment-mode"] = "edge"
        hosted_data["ppas-to-proxy"] = ""
        hosted_data["supported-releases"] = ""
        hosted_data["gpg-passphrase-path"] = "/etc/landscape/gpg-passphrase"
        hosted_data["gpg-home-path"] = "/etc/landscape/gpg"
        self.hookenv.relations.update({
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/0": hosted_data,
                },
            },
        })
        self.hook()
        self.assertIsNotNone(os.lstat(self.paths.config_link("edge")))

    def test_ready_write_ssl_cert(self):
        """
        When the data is ready the custom SSL certificate data gets
        written on disk.
        """
        self.hook()
        self.assertTrue(os.path.exists(self.paths.ssl_certificate()))

    def test_ready_with_openid_configuration(self):
        """
        OpenID configuration is passed in to service.conf generation if
        it is set in the hook configuration.
        """
        self.hookenv.config().update(SAMPLE_CONFIG_OPENID_DATA)
        self.hook()
        config_expected = SAMPLE_CONFIG_OPENID_DATA.copy()
        config_expected["worker-counts"] = SAMPLE_WORKER_COUNT_DATA

        rendered_context = self.renders[0][2]
        self.assertEqual(config_expected, rendered_context["config"])

    def test_ready_with_oidc_configuration(self):
        """
        OpenID-Connect configuration is passed in to service.conf generation if
        it is set in the hook configuration.
        """
        self.hookenv.config().update(SAMPLE_CONFIG_OIDC_DATA)
        self.hook()
        config_expected = SAMPLE_CONFIG_OIDC_DATA.copy()
        config_expected["worker-counts"] = SAMPLE_WORKER_COUNT_DATA

        rendered_context = self.renders[0][2]
        self.assertEqual(config_expected, rendered_context["config"])

    def test_remote_leader_not_ready(self):
        """
        If we're not the leader unit and we didn't yet get relation data from
        the leader, we are not ready.
        """
        self.hookenv.leader = False
        self.hook()
        self.assertIn(
            ("Incomplete data: LeaderRequirer", "DEBUG"),
            self.hookenv.messages)

    def test_remote_leader_ready(self):
        """
        If we're not the leader unit and we got leader data from the leader,
        along with the rest of required relations, then we're good.
        """
        self.hookenv.leader = False
        self.hookenv.leader_set(SAMPLE_LEADER_DATA)
        self.hook()
        self.assertEqual(2, len(self.renders))

    def test_license_file(self):
        """
        License file is created when license-file option is set in the config.
        """
        self.hookenv.config().update(SAMPLE_CONFIG_LICENSE_DATA)
        self.hook()

        self.assertEqual(
            [("write_file", (self.paths.license_file(), "license data"),
              {"owner": "landscape", "group": "root", "perms": 0o640})],
            self.host.calls)

    def test_apt_source(self):
        """
        If the source config changes, APT sources are refreshed.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config["source"] = "ppa:landscape/15.01"
        self.hook()
        self.assertTrue(len(self.fetch.sources) == 1)

    def test_ssl_cert_changed(self):
        """
        If the SSL certificate changes, the relation with haproxy gets updated.
        """
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config.save()
        config["ssl-cert"] = base64.b64encode(b"<cert>")
        config["ssl-key"] = base64.b64encode(b"<key>")
        self.hook()
        data = yaml.load(self.hookenv.relations["website:1"]["services"])
        self.assertIsNotNone(data)

    def test_leader_elected(self):
        """
        When a leader is elected, the ServicesHook sets the haproxy
        relation data.
        """
        self.hookenv.hook = "leader-elected"
        self.hook()
        data = yaml.load(self.hookenv.relations["website:1"]["services"])
        self.assertIsNotNone(data)

    def test_worker_count_changed(self):
        """
        If the count of service workers changes, /etc/default/landscape-server
        is rendered with the new counts.
        """
        self.hookenv.hook = "config-changed"
        config = self.hookenv.config()
        config.save()
        config["worker-counts"] = 7
        self.hook()
        # Config option is turned into a per-service worker count.
        _, _, context, _, _, _ = self.renders[1]
        self.assertEqual(
            {"appserver": 2, "pingserver": 7, "message-server": 7},
            context["config"]["worker-counts"])
