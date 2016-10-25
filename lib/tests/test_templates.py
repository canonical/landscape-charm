from ConfigParser import ConfigParser
from cStringIO import StringIO

from lib.tests.helpers import TemplateTest
from lib.tests.sample import (
    SAMPLE_DB_UNIT_DATA, SAMPLE_LEADER_CONTEXT_DATA, SAMPLE_AMQP_UNIT_DATA,
    SAMPLE_HOSTED_DATA, SAMPLE_WORKER_COUNT_DATA, SAMPLE_WEBSITE_UNIT_DATA)


class ServiceConfTest(TemplateTest):

    template_filename = "service.conf"

    def setUp(self):
        super(ServiceConfTest, self).setUp()
        self.context = {
            "db": [SAMPLE_DB_UNIT_DATA.copy()],
            "amqp": [SAMPLE_AMQP_UNIT_DATA.copy()],
            "website": [SAMPLE_WEBSITE_UNIT_DATA.copy()],
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

    def test_render_with_openid_both_required(self):
        """
        When only one of OpenID configuration keys is present, neither
        openid-related options are set.
        """
        config = self.context["config"]
        config.update({
            "openid-provider-url": "http://openid-host/",
        })
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertFalse(config.has_option("landscape", "openid-provider-url"))
        self.assertFalse(config.has_option("landscape", "openid-logout-url"))

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
        self.assertEqual("9099", config.get("package-search", "port"))
        self.assertEqual(
            "main package resource-1", config.get("package-search", "stores"))
        self.assertEqual(
            "/var/run/landscape/landscape-package-search.pid",
            config.get("package-search", "pid-path"))
        self.assertEqual(
            "800", config.get("package-search", "account-threshold"))

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
        self.context["website"][0]["public-address"] = "4.3.2.1"

        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual("https://4.3.2.1/", config.get("global", "root-url"))
        self.assertEqual("https://4.3.2.1/", config.get("api", "root-url"))
        self.assertEqual(
            "https://4.3.2.1/", config.get("package-upload", "root-url"))

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
        self.assertEqual("https://8.8.8.8/", config.get("api", "root-url"))
        self.assertEqual(
            "https://8.8.8.8/", config.get("package-upload", "root-url"))

    def test_render_with_pppa_proxy(self):
        """
        With ppas-to-proxy defined in the hosted relation, pppa-proxy section
        is added to the service configuration listing URLs for all PPAs.
        """
        self.context["hosted"][0].update({
            "ppas-to-proxy": {
                "16.03": "http://ppa.launchpad.net/landscape/16.03/ubuntu",
                "16.06": "http://ppa.launchpad.net/landscape/16.06/ubuntu",
            },
        })
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual(
            "http://ppa.launchpad.net/landscape/16.03/ubuntu",
            config.get("pppa-proxy", "16.03-url"))
        self.assertEqual(
            "http://ppa.launchpad.net/landscape/16.06/ubuntu",
            config.get("pppa-proxy", "16.06-url"))

    def test_render_with_pppa_proxy_supported_releases(self):
        """
        With supported-releases defined in the hosted relation, pppa-proxy
        section with the "supported-releases" key.
        """
        self.context["hosted"][0].update({
            "supported-releases": ["16.03", "16.06"],
            # It's required to have ppas-to-proxy to even get the pppa-proxy
            # config section.
            "ppas-to-proxy": {"16.03": "foo"},
        })
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual(
            "16.03 16.06", config.get("pppa-proxy", "supported-releases"))

    def test_render_with_gpg_options(self):
        """
        With gpg-home-path and gpg-passphrase-path defined in the hosted
        relation, landscape and api sections get them too.
        """
        self.context["hosted"][0].update({
            "gpg-home-path": "/etc/landscape/gpg",
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
        })
        buffer = StringIO(self.template.render(self.context))
        config = ConfigParser()
        config.readfp(buffer)
        self.assertEqual(
            "/etc/landscape/gpg", config.get("landscape", "gpg-home-path"))
        self.assertEqual(
            "/etc/landscape/gpg-passphrase.txt",
            config.get("landscape", "gpg-passphrase-path"))
        self.assertEqual(
            "/etc/landscape/gpg", config.get("api", "gpg-home-path"))
        self.assertEqual(
            "/etc/landscape/gpg-passphrase.txt",
            config.get("api", "gpg-passphrase-path"))


class LandscapeDefaultsTest(TemplateTest):

    template_filename = "landscape-server"

    def setUp(self):
        super(LandscapeDefaultsTest, self).setUp()
        self.context = {
            "hosted": [SAMPLE_HOSTED_DATA.copy()],
            "config": {"worker-counts": SAMPLE_WORKER_COUNT_DATA},
            "is_leader": True,
        }

    def test_render_on_leader(self):
        """
        The landscape-server template renders Landscape default configuration
        in /etc/default/landscape-server, which configures services to run
        on a particular unit. On leader units cron jobs and juju-sync are on.
        """
        buffer = self.template.render(self.context)
        self.assertIn('RUN_CRON="yes"\n', buffer)
        self.assertIn('RUN_JUJU_SYNC="yes"\n', buffer)

    def test_render_on_non_leader(self):
        """
        On a non-leader unit, cron scripts are not enabled by default.
        """
        self.context["is_leader"] = False
        buffer = self.template.render(self.context)
        self.assertIn('RUN_CRON="no"\n', buffer)

    def test_render_juju_sync(self):
        """
        If the landscape-server unit is the leader and we're in standalone
        mode, juju-sync will be run.
        """
        buffer = self.template.render(self.context)
        self.assertIn('RUN_JUJU_SYNC="yes"\n', buffer)

    def test_render_juju_sync_not_leader(self):
        """
        If the landscape-server unit is not the leader, juju-sync
        won't be run.
        """
        self.context["is_leader"] = False
        buffer = self.template.render(self.context)
        self.assertIn('RUN_JUJU_SYNC="no"\n', buffer)

    def test_render_juju_sync_not_standalone(self):
        """
        If the deployment mode is not standalone, juju-sync won't be run.
        """
        hosted_data = self.context["hosted"][0]
        hosted_data["deployment-mode"] = "production"
        buffer = self.template.render(self.context)
        self.assertIn('RUN_JUJU_SYNC="no"\n', buffer)

    def test_render_ppa_proxy_nothing_by_default(self):
        """
        By default RUN_PPPA_PROXY is not rendered at all.
        """
        buffer = self.template.render(self.context)
        self.assertNotIn('RUN_PPPA_PROXY', buffer)

    def test_render_ppa_proxy(self):
        """
        If hosted relation provides ppas-to-proxy, RUN_PPPA_PROXY is added.
        """
        self.context["hosted"][0]["ppas-to-proxy"] = {
            "16.06": "http://ppa.launchpad.net/landscape/16.06/ubuntu",
        }
        buffer = self.template.render(self.context)
        self.assertIn('RUN_PPPA_PROXY="yes"\n', buffer)

    def test_render_package_search(self):
        """
        If the landscape-server unit is the leader, package-search will be run.
        """
        buffer = self.template.render(self.context)
        self.assertIn('RUN_PACKAGESEARCH="yes"\n', buffer)

    def test_render_package_search_not_leader(self):
        """
        If the landscape-server unit is not the leader, package-search will
        not be run.
        """
        self.context["is_leader"] = False
        buffer = self.template.render(self.context)
        self.assertIn('RUN_PACKAGESEARCH="no"\n', buffer)

    def test_render_worker_counts(self):
        """
        Rendering landscape-server file sets RUN_PINGSERVER and
        RUN_MSGSERVER both to 2 from the sample worker count configuration.
        """
        buffer = self.template.render(self.context)
        self.assertIn('RUN_APPSERVER="2"\n', buffer)
        self.assertIn('RUN_PINGSERVER="2"\n', buffer)
        self.assertIn('RUN_MSGSERVER="2"\n', buffer)

    def test_render_deployed_from(self):
        """
        When deployed from charm, it contains DEPLOYED_FROM to indicate that.
        """
        buffer = self.template.render(self.context)
        self.assertIn('DEPLOYED_FROM="charm"\n', buffer)
