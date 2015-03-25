from ConfigParser import ConfigParser
from cStringIO import StringIO


from lib.tests.helpers import TemplateTest
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA,
    SAMPLE_LEADER_CONTEXT_DATA_WITH_OPENID, SAMPLE_AMQP_UNIT_DATA)


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

    def test_render_with_openid(self):
        """
        When OpenID configuration is present in the leader context,
        openid-related options are set.
        """
        context = {
            "db": [SAMPLE_DB_UNIT_DATA],
            "amqp": [SAMPLE_AMQP_UNIT_DATA],
            "leader": SAMPLE_LEADER_CONTEXT_DATA_WITH_OPENID,
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
