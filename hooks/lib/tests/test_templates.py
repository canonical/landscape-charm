from ConfigParser import ConfigParser
from cStringIO import StringIO


from lib.tests.helpers import TemplateTest


class ServiceConfTest(TemplateTest):

    template_filename = "service.conf"

    def test_render_stores(self):
        """
        The service.conf template renders data about PostgreSQL configuration.
        """
        context = {
            "db": [{
                "database": "all",
                "host": "1.2.3.4",
                "password": "sekret",
                "port": "5432",
                "user": "admin"
            }]
        }
        buffer = StringIO(self.template.render(context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("1.2.3.4:5432", config.get("stores", "host"))
        self.assertEqual("admin", config.get("schema", "store_user"))
        self.assertEqual("sekret", config.get("schema", "store_password"))
