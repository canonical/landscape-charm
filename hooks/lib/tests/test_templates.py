from ConfigParser import ConfigParser
from cStringIO import StringIO

from lib.tests.helpers import TemplateTest
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA, SAMPLE_AMQP_UNIT_DATA,
    SAMPLE_HOSTED_DATA, SAMPLE_WEBSITE_UNIT_DATA)


class ServiceConfTest(TemplateTest):

    template_filename = "service.conf"

    def setUp(self):
        super(ServiceConfTest, self).setUp()
        self.context = {
            "db": [SAMPLE_DB_UNIT_DATA.copy()],
            "amqp": [SAMPLE_AMQP_UNIT_DATA.copy()],
            "haproxy": SAMPLE_WEBSITE_UNIT_DATA,
            "leader": SAMPLE_LEADER_CONTEXT_DATA.copy(),
            "hosted": [SAMPLE_HOSTED_DATA.copy()],
            "config": {},
            "is_leader": False,
        }

    def test_render(self):
        """
        The service.conf template renders data about generic Landscape
        configuration which includes PostgreSQL configuration, AMQP
        configuration, secret token and no OpenID settings by default.
        """
        buffer = StringIO(self.template.render(self.context))
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
        config = self.context["config"]
        config.update({
            "openid-provider-url": "http://openid-host/",
            "openid-logout-url": "http://openid-host/logout",
        })
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual(
            "http://openid-host/",
            config.get("landscape", "openid-provider-url"))
        self.assertEqual(
            "http://openid-host/logout",
            config.get("landscape", "openid-logout-url"))

    def test_render_with_package_search_on_leader(self):
        """
        The service.conf file on the leader has a package-search host set
        to localhost.
        """
        self.context["is_leader"] = True
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("localhost", config.get("package-search", "host"))
        self.assertEqual("9250", config.get("package-search", "port"))
        self.assertEqual(
            "main package resource-1", config.get("package-search", "stores"))
        self.assertEqual(
            "/srv/landscape.canonical.com/var/landscape-package-search.pid",
            config.get("package-search", "pid-path"))
        self.assertEqual(
            "1000", config.get("package-search", "account-threshold"))

    def test_render_with_package_search_on_non_leader(self):
        """
        The serice.conf file on a non-leader unit has a package-search host set
        to the leader's IP address.
        """
        self.context["leader"]["leader-ip"] = "1.2.3.4"
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("1.2.3.4", config.get("package-search", "host"))

    def test_render_with_haproxy_address_as_root_url(self):
        """
        The service.conf file has root-url set to the haproxy public IP if the
        config doesn't have a root-url entry.
        """
        self.context["haproxy"]["public-address"] = "4.3.2.1"

        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("https://4.3.2.1/", config.get("global", "root-url"))

    def test_render_with_config_provided_root_url(self):
        """
        The service.conf file has root-url set to the content of the root-url
        charm config option if it is specified.
        """
        self.context["config"]["root-url"] = "https://8.8.8.8/"
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("https://8.8.8.8/", config.get("global", "root-url"))


class LandscapeDefaultsTest(TemplateTest):

    template_filename = "landscape-server"

    def setUp(self):
        super(LandscapeDefaultsTest, self).setUp()
        self.context = {
            "hosted": [SAMPLE_HOSTED_DATA.copy()],
            "config": {},
            "is_leader": True,
        }

    def test_render_on_leader(self):
        """
        The landscape-server template renders Landscape default configuration
        in /etc/default/landscape-server, which configures services to run
        on a particular unit. On leader units cron jobs and juju-sync are on.
        """
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_CRON="yes"\n', buffer)
        self.assertIn('RUN_JUJU_SYNC="yes"\n', buffer)

    def test_render_on_non_leader(self):
        """
        On a non-leader unit, cron scripts are not enabled by default.
        """
        self.context["is_leader"] = False
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_CRON="no"\n', buffer)

    def test_render_juju_sync(self):
        """
        If the landscape-server unit is the leader and we're in standalone
        mode, juju-sync will be run.
        """
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_JUJU_SYNC="yes"\n', buffer)

    def test_render_juju_sync_not_leader(self):
        """
        If the landscape-server unit is not the leader, juju-sync
        won't be run.
        """
        self.context["is_leader"] = False
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_JUJU_SYNC="no"\n', buffer)

    def test_render_juju_sync_not_standalone(self):
        """
        If the deployment mode is not standalone, juju-sync won't be run.
        """
        hosted_data = self.context["hosted"][0]
        hosted_data["deployment-mode"] = "production"
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_JUJU_SYNC="no"\n', buffer)

    def test_render_package_search(self):
        """
        If the landscape-server unit is the leader, package-search will be run.
        """
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_PACKAGESEARCH="yes"\n', buffer)

    def test_render_package_search_not_leader(self):
        """
        If the landscape-server unit is not the leader, package-search will
        not be run.
        """
        self.context["is_leader"] = False
        buffer = StringIO(self.template.render(self.context)).readlines()
        self.assertIn('RUN_PACKAGESEARCH="no"\n', buffer)
