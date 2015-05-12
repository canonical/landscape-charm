"""
This test creates a real landscape deployment, and runs some checks against it.

FIXME: revert to using ssh -q, stderr=STDOUT instead of 2>&1, stderr=PIPE once
       lp:1281577 is addressed.
"""

import unittest

from configparser import ConfigParser
from os import getenv
from subprocess import check_output, CalledProcessError, PIPE

from helpers import (
    check_url, get_landscape_service_conf, run_command_on_unit, IntegrationTest)


class ServiceTest(IntegrationTest):

    def setUp(self):
        super(ServiceTest, self).setUp()
        self.frontend = self.environment.get_haproxy_public_address()

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

    def test_no_broker_defaults(self):
        """Verify that [broker] has no default values.

        This test verifies that the host and password configuration keys
        from the [broker] section don't remain at their default values.
        """
        config = ConfigParser()
        config.read_string(get_landscape_service_conf("landscape-server/0"))
        broker = config["broker"]
        self.assertNotEqual(broker["host"], "localhost")
        self.assertNotEqual(broker["password"], "landscape")

    def test_app_unavailable_page(self):
        """
        Verify that the frontend shows the styled unavailable page.
        """
        self.environment.stop_landscape_service("landscape-appserver")
        good_content = "please phone us"
        url = "https://{}/".format(self.frontend)
        check_url(url, good_content)

    @unittest.expectedFailure
    def test_msg_unavailable_page(self):
        """
        Verify that the frontend shows the unstyled unavailable page for msg.
        """
        self.environment.stop_landscape_service("landscape-msgserver")
        good_content = ["503 Service Unavailable",
                        "No server is available to handle this request."]
        url = "https://{}/message-system".format(self.frontend)
        check_url(url, good_content)

    @unittest.expectedFailure
    def test_ping_unavailable_page(self):
        """
        Verify that the frontend shows the unstyled unavailable page for ping.
        """
        self.environment.stop_landscape_service("landscape-pingserver")
        good_content = ["503 Service Unavailable",
                        "No server is available to handle this request."]
        url = "http://{}/ping".format(self.frontend)
        check_url(url, good_content)

    def test_ssl_certificate_is_in_place(self):
        """
        The landscape-server charm looks at the SSL certificate set on the
        relation with haproxy and writes it on disk in the location that
        the application expects (it will need it when generating client
        configuration for Autopilot deployments).
        """
        ssl_cert = run_command_on_unit(
            "cat /etc/ssl/certs/landscape_server_ca.crt", "landscape-server/0")
        self.assertTrue(ssl_cert.startswith("-----BEGIN CERTIFICATE-----"))


class CronTest(IntegrationTest):
    """Host all the tests that expects the cron daemon to be stopped.

    The deployment will the same minimal one from OneLandscapeUnitTest, but
    the cron daemon will be stopped, so Landscape cron jobs in particular
    won't be run.
    """
    cron_unit = "landscape-server/0"

    @classmethod
    def setUpClass(cls):
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
        cmd = ["juju", "run", "--unit", "landscape-server/0", find_cmd]
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

    def test_root_url_is_set(self):
        """root_url should be set in the postgres db."""
        config = ConfigParser()
        config.read_string(get_landscape_service_conf("landscape-server/0"))
        frontend = self.environment.get_haproxy_public_address()
        self.assertEqual(
            "https://%s/" % frontend, config["global"]["root-url"])

    @staticmethod
    def _stop_cron(unit):
        cmd = ["juju", "ssh", unit, "sudo", "service", "cron", "stop", "2>&1"]
        check_output(cmd, stderr=PIPE)

    @staticmethod
    def _start_cron(unit):
        cmd = ["juju", "ssh", unit, "sudo", "service", "cron", "start", "2>&1"]
        check_output(cmd, stderr=PIPE)
