from lib.tests.helpers import HookenvTest
from lib.relations.config import ConfigRequirer
from lib.relations.application_dashboard import ApplicationDashboardProvider


class ApplicationDashboardProviderTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(ApplicationDashboardProviderTest, self).setUp()
        self.config_requirer = ConfigRequirer(hookenv=self.hookenv)

    def test_provide_data(self):
        """Data provider fills relation from config."""
        site_name = "test"
        config = self.hookenv.config()
        config["site-name"] = site_name
        config["root-url"] = "https://landscape.com"
        subtitle = "[{}] Systems management".format(site_name)
        group = "[{}] LMA".format(site_name)

        relation = ApplicationDashboardProvider(
            self.config_requirer,
            hookenv=self.hookenv)
        data = relation.provide_data()

        expected = {
            "name": "Landscape",
            "url": "https://landscape.com",
            "subtitle": subtitle,
            "icon": None,
            "group": group,
        }
        self.assertEqual(expected, data)
