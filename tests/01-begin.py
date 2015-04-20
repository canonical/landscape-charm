#!/usr/bin/python3
"""
This test creates a real landscape deployment, and runs some checks against it.

FIXME: revert to using ssh -q, stderr=STDOUT instead of 2>&1, stderr=PIPE once
       lp:1281577 is addressed.
"""

import logging
import unittest

import jujulib.deployer

from os.path import dirname, abspath, join
from configparser import ConfigParser
from os import getenv
from subprocess import check_output, CalledProcessError, PIPE
from glob import glob

from helpers import (
    check_url, juju_status, find_address, get_landscape_units,
    get_landscape_service_conf, BaseLandscapeTests)


log = logging.getLogger(__file__)


def setUpModule():
    """Deploys Landscape via the charm. All the tests use this deployment."""
    deployer = jujulib.deployer.Deployer()
    charm_dir = dirname(dirname(abspath(__file__)))
    bundles = glob(join(charm_dir, "bundles", "*.yaml"))
    deployer.deploy(getenv("DEPLOYER_TARGET", "landscape-scalable"), bundles,
                    timeout=3000)

    frontend = find_address(juju_status(), "haproxy")

    # Make sure the app server is up.
    # Note: In order to work on a new server or a server with the
    #       first admin user already created, this phrase should match
    #       the new-standalone-user form, the login form, and not
    #       the maintenance page.
    good_content = "passphrase"
    log.info("Polling. Waiting for app server: {}".format(frontend))
    check_url("https://{}/".format(frontend), good_content, interval=30,
              attempts=10, retry_unavailable=True)


class LandscapeServiceTests(BaseLandscapeTests):
    """
    Class hosting all the tests we want to run against a Landscape deployment.
    """

    @classmethod
    def setUpClass(cls):
        """Prepares juju_status which many tests use."""
        cls.juju_status = juju_status()
        cls.frontend = find_address(cls.juju_status, "haproxy")

    def test_app(self):
        """Verify that the APP service is up.

        Specifically that it is reachable and that it presents the new
        user form.

        Note: In order to work on a new server or a server with the
          first admin user already created, this phrase should match
          the new-standalone-user form, the login form, and not
          the maintenance page.
        """
        good_content = "passphrase"
        check_url("https://{}/".format(self.frontend), good_content)

    def test_msg(self):
        """Verify that the MSG service is up.

        Specifically that it is reachable and that it responds
        correctly to requests.
        """
        good_content = ["ds8:messagesl", "s11:server-uuid"]
        post_data = ("ds8:messagesl;s22:next-expected-sequencei0;s8:"
                     "sequencei0;;")
        header = "X-MESSAGE-API: 3.1"
        check_url("https://{}/message-system".format(self.frontend),
                  good_content, post_data, header)

    def test_ping(self):
        """Verify that the PING service is up.

        Specifically that it is reachable and that it responds
        correctly to a ping request without an ID.
        """
        good_content = "ds5:errors19:provide insecure_id;"
        check_url("http://{}/ping".format(self.frontend), good_content)

    def test_api(self):
        """Verify that the API service is up.

        Specifically that it is reachable and returns its name.
        """
        good_content = "Query API Service"
        check_url("https://{}/api".format(self.frontend), good_content)

    @unittest.skip("currently oopses")
    def test_upload(self):
        """Verify that the PACKAGE UPLOAD service is up.

        Specifically that it is reachable and returns its name.
        """
        good_content = "Landscape package upload service"
        # ending / is important because of the way we wrote this RewriteRule
        url = "https://{}/upload/".format(self.frontend)
        check_url(url, good_content)


class LandscapeServiceConfigTests(BaseLandscapeTests):

    @classmethod
    def setUpClass(cls):
        """Prepare landscape_service_conf which will be used by the tests."""
        landscape_units = []
        cls.juju_status = juju_status()
        cls.landscape_service_conf = []
        landscape_units = get_landscape_units(cls.juju_status)
        for unit in landscape_units:
            config = ConfigParser()
            config.read_string(get_landscape_service_conf(unit))
            cls.landscape_service_conf.append(config)

    def test_no_broker_defaults(self):
        """Verify that [broker] has no default values.

        This test verifies that the host and password configuration keys
        from the [broker] section don't remain at their default values.
        """
        for config in self.landscape_service_conf:
            broker = config["broker"]
            self.assertNotEqual(broker["host"], "localhost")
            self.assertNotEqual(broker["password"], "landscape")


class LandscapeErrorPagesTests(BaseLandscapeTests):

    @classmethod
    def setUpClass(cls):
        """Prepares juju_status and other attributes that many tests use."""
        cls.juju_status = juju_status()
        cls.frontend = find_address(cls.juju_status, "haproxy")
        cls.landscape_units = get_landscape_units(cls.juju_status)
        cls.first_unit = cls.landscape_units[0]

    def run_command_on_unit(self, cmd, unit):
        output = check_output(["juju", "ssh", unit, cmd], stderr=PIPE)
        return output.decode("utf-8").strip()

    def stop_server(self, name, unit):
        cmd = "sudo service %s stop" % name
        self.run_command_on_unit(cmd, unit)

    def start_server(self, name, unit):
        cmd = "sudo service %s start" % name
        self.run_command_on_unit(cmd, unit)

    def test_app_unavailable_page(self):
        """
        Verify that the frontend shows the styled unavailable page.
        """
        self.addCleanup(self.start_server, "landscape-appserver",
                        self.first_unit)
        self.stop_server("landscape-appserver", self.first_unit)
        good_content = "please phone us"
        url = "https://{}/".format(self.frontend)
        check_url(url, good_content)

    @unittest.expectedFailure
    def test_msg_unavailable_page(self):
        """
        Verify that the frontend shows the unstyled unavailable page for msg.
        """
        self.addCleanup(self.start_server, "landscape-msgserver",
                        self.first_unit)
        self.stop_server("landscape-msgserver", self.first_unit)
        good_content = ["503 Service Unavailable",
                        "No server is available to handle this request."]
        url = "https://{}/message-system".format(self.frontend)
        check_url(url, good_content)

    @unittest.expectedFailure
    def test_ping_unavailable_page(self):
        """
        Verify that the frontend shows the unstyled unavailable page for ping.
        """
        self.addCleanup(self.start_server, "landscape-pingserver",
                        self.first_unit)
        self.stop_server("landscape-pingserver", self.first_unit)
        good_content = ["503 Service Unavailable",
                        "No server is available to handle this request."]
        url = "http://{}/ping".format(self.frontend)
        check_url(url, good_content)


class LandscapeCronTests(BaseLandscapeTests):

    @classmethod
    def setUpClass(cls):
        cls.juju_status = juju_status()
        cls.cron_unit = get_landscape_units(cls.juju_status)[0]
        cls._stop_cron(cls.cron_unit)

    @classmethod
    def tearDownClass(cls):
        cls._start_cron(cls.cron_unit)

    def _sanitize_ssh_output(self, output,
                             remove_text=["sudo: unable to resolve",
                                          "Warning: Permanently added"]):
        """Strip some common warning messages from ssh output.

        @param output: output to sanitize
        @param remove_text: list of text that, if found at the beginning of
                            the a output line, will have that line removed
                            entirely.
        """
        new_output = []
        for line in output.split("\n"):
            if any(line.startswith(remove) for remove in remove_text):
                continue
            new_output.append(line)
        return "\n".join(new_output)

    def _run_cron(self, script):
        status = 0
        cmd = ["juju", "ssh", self.cron_unit, "sudo", "-u landscape", script,
               "2>&1"]
        try:
            # The sanitize is a workaround for lp:1328269
            output = self._sanitize_ssh_output(
                check_output(cmd, stderr=PIPE).decode("utf-8").strip())
        except CalledProcessError as e:
            output = e.output.decode("utf-8").strip()
            status = e.returncode
        # these jobs currently don't set their exit status to non-zero
        # if they fail, they just print things to stdout/stderr
        return (output, status)

    def test_maintenance_cron(self):
        """Verify that the maintenance cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/maintenance.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    def test_update_security_db_cron(self):
        """Verify that the update_security_db cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/update_security_db.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    @unittest.skip("fails to acquire the lock needs debugging")
    def test_update_alerts_cron(self):
        """Verify that the update_alerts cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/update_alerts.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    def test_landscape_profiles_cron(self):
        """Verify that the landscape_profiles cron job runs without errors."""

        # process_profiles renamed to landscape_profiles on trunk @ r8238
        find_cmd = (
            "sudo ls /opt/canonical/landscape/scripts/landscape_profiles.sh"
            " || sudo ls /opt/canonical/landscape/scripts/process_profiles.sh")
        cmd = ["juju", "run", "--unit", "landscape/0", find_cmd]
        script = check_output(cmd, stderr=PIPE).decode("utf-8").strip()

        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    def test_process_alerts_cron(self):
        """Verify that the process_alerts cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/process_alerts.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    @unittest.skipIf(getenv("SKIP_SLOW_TESTS", None),
                     "Requested to skip slow tests.")
    def test_hash_id_databases_cron(self):
        """Verify that the hash_id_databases cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/hash_id_databases.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    def test_meta_releases_cron(self):
        """Verify that the meta_releases cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/meta_releases.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    def test_sync_lds_releases_cron(self):
        """Verify that the sync_lds_releases cron job runs without errors."""
        script = "/opt/canonical/landscape/scripts/sync_lds_releases.sh"
        output, status = self._run_cron(script)
        self.assertEqual(output, "")
        self.assertEqual(status, 0)

    @unittest.expectedFailure
    def test_root_url_is_set(self):
        """root_url should be set in the postgres db."""
        frontend = find_address(juju_status(), "haproxy")
        psql_cmd = "sudo -u postgres psql -At landscape-main " \
            "-c \"select encode(key, 'escape'),encode(value, 'escape') " \
            "from system_configuration where key='landscape.root_url'\" " \
            " 2>/dev/null"
        cmd = ["juju", "run", "--unit", "postgresql/0", psql_cmd]
        output = check_output(cmd, stderr=PIPE).decode("utf-8").strip()
        self.assertIn(frontend, output)

    @staticmethod
    def _stop_cron(unit):
        cmd = ["juju", "ssh", unit, "sudo", "service", "cron", "stop", "2>&1"]
        check_output(cmd, stderr=PIPE)

    @staticmethod
    def _start_cron(unit):
        cmd = ["juju", "ssh", unit, "sudo", "service", "cron", "start", "2>&1"]
        check_output(cmd, stderr=PIPE)


if __name__ == "__main__":
    logging.basicConfig(
        level='DEBUG', format='%(asctime)s %(levelname)s %(message)s')
    unittest.main(verbosity=2)
