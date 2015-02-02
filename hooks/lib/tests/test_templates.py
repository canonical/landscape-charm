from ConfigParser import ConfigParser
from cStringIO import StringIO


from lib.tests.helpers import TemplateTest
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA, SAMPLE_AMQP_UNIT_DATA)


class ServiceConfTest(TemplateTest):

    template_filename = "service.conf"

    def test_render_stores(self):
        """
        The service.conf template renders data about PostgreSQL configuration.
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
