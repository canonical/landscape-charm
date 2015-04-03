from ConfigParser import ConfigParser
from cStringIO import StringIO


from lib.tests.helpers import TemplateTest
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA, SAMPLE_AMQP_UNIT_DATA,
    SAMPLE_HOSTED_DATA)


class ServiceConfTest(TemplateTest):

    template_filename = "service.conf"

    def test_render(self):
        """
        The service.conf template renders data about generic Landscape
        configuration which includes PostgreSQL configuration, AMQP
        configuration, secret token and no OpenID settings by default.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {},
        }
        buffer = StringIO(self.template.render(context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("10.0.3.168:5432", config.get("stores", "host"))
        self.assertEqual("db_admin_1", config.get("schema", "store_user"))
        self.assertEqual("sekret", config.get("schema", "store_password"))
        self.assertEqual("landscape-sekret", config.get("stores", "password"))
        self.assertEqual("10.0.3.170", config.get("broker", "host"))
        self.assertEqual("guessme", config.get("broker", "password"))
        self.assertEqual(
            "landscape-token", config.get("landscape", "secret-token"))
        self.assertFalse(config.has_option("landscape", "openid-provider-url"))
        self.assertFalse(config.has_option("landscape", "openid-logout-url"))
        self.assertEqual("standalone", config.get("global", "deployment-mode"))

    def test_render_with_openid(self):
        """
        When OpenID configuration is present in the leader context,
        openid-related options are set.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {
                "openid-provider-url": "http://openid-host/",
                "openid-logout-url": "http://openid-host/logout",
            },
        }
        buffer = StringIO(self.template.render(context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual(
            "http://openid-host/",
            config.get("landscape", "openid-provider-url"))
        self.assertEqual(
            "http://openid-host/logout",
            config.get("landscape", "openid-logout-url"))


class LandscapeDefaultsTest(TemplateTest):

    template_filename = "landscape-server"

    def test_render(self):
        """
        The landscape-server template renders Landscape default configuration
        in /etc/default/landscape-server, which configures services to run
        on a particular unit.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {},
            "is_leader": True,
        }
        buffer = StringIO(self.template.render(context)).readlines()
        self.assertIn('RUN_CRON="yes"\n', buffer)

    def test_render_on_non_leader(self):
        """
        On a non-leader unit, cron scripts are not enabled by default.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {},
            "is_leader": False,
        }
        buffer = StringIO(self.template.render(context)).readlines()
        self.assertIn('RUN_CRON="no"\n', buffer)

    def test_render_juju_sync(self):
        """
        If the landspape-server unit is the leader and we're in standalone
        mode, juju-sync will be run.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {},
            "is_leader": True,
        }
        buffer = StringIO(self.template.render(context)).readlines()
        self.assertIn('RUN_JUJU_SYNC="yes"\n', buffer)

    def test_render_juju_sync_not_leader(self):
        """
        If the landspape-server unit is not the leader, juju-sync
        won't be run.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [SAMPLE_HOSTED_DATA],
            "config": {},
            "is_leader": False,
        }
        buffer = StringIO(self.template.render(context)).readlines()
        self.assertIn('RUN_JUJU_SYNC="no"\n', buffer)

    def test_render_juju_sync_not_standalone(self):
        """
        If the deployment mode is not standalone, juju-sync won't be run.
        """
        hosted_data = SAMPLE_HOSTED_DATA.copy()
        hosted_data["deployment-mode"] = "production"
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA,
            "hosted": [hosted_data],
            "config": {},
            "is_leader": True,
        }
        buffer = StringIO(self.template.render(context)).readlines()
        self.assertIn('RUN_JUJU_SYNC="no"\n', buffer)
