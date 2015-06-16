"""
Common helpers for landscpae integration tests.
"""

import logging
import sys
import yaml
import os
import subprocess
import tempfile
import shutil
import json
import time

from operator import itemgetter
from os import getenv
from time import sleep
from configparser import ConfigParser

from fixtures import Fixture, TestWithFixtures

from amulet import Deployment

from zope.testrunner import run

from jinja2 import FileSystemLoader, Environment

log = logging.getLogger(__file__)

# Default values for rendering the bundle jinja2 template
DEFAULT_BUNDLE_CONTEXT = {
    "name": "test",
    "rabbitmq": {},
    "postgresql": {
        "max_connections": 100,
        "memory": 128,
        "manual_tuning": getenv("PG_MANUAL_TUNING", "1") == "1",
        "shared_buffers": "64MB",
        "checkpoint_segments": 64,
        "maintenance_work_mem": "64MB",
        "work_mem": "64MB",
        "effective_cache_size": "64MB",
        },
    "haproxy": {},
    "landscape": {
        "memory": 128},
}


class EnvironmentFixture(Fixture):
    """Set the initial environment by passing the testing bundle to Amulet.

    This fixture also acts as API for driving Amulet as needed by the tests.

    The LS_CHARM_SOURCE environment variable can be used to set the 'source'
    charm config option of the deployed landscape-server service. See the
    metadata.yaml file for possible configuration values.
    """

    _timeout = 3000
    _series = "trusty"
    _deployment = Deployment(series=_series)

    def __init__(self, config=None, deployment=None, subprocess=subprocess):
        """
        @param config: Optionally a dict with extra bundle template context
            values. It will be merged into DEFAULT_BUNDLE_CONTEXT when
            deploying the test bundle.
        """
        self._config = config or {}
        if deployment is not None:
            self._deployment = deployment
        self._subprocess = subprocess

    def setUp(self):
        super(EnvironmentFixture, self).setUp()
        if not self._deployment.deployed:
            self._deployment.load(self._get_bundle())
            repo_dir = self._build_repo_dir()
            try:
                self._deployment.setup(timeout=self._timeout)
            finally:
                self._clean_repo_dir(repo_dir)
            self._deployment.sentry.wait(self._timeout)

    def get_haproxy_public_address(self, unit=None):
        """Return the public address of the given haproxy unit."""
        unit = self._get_service_unit("haproxy", unit=unit)
        return unit.info["public-address"]

    def get_binary_file(self, path, service, unit=None):
        """Return the content of a binary file on the given unit."""
        # XXX: Amulet doesn't support getting binary files, so we
        # get it as a text file and get the binary data from the
        # UnicodeDecodeError exception.
        try:
            contents = self.get_text_file(path, service, unit=unit)
        except UnicodeDecodeError as error:
            return error.object
        else:
            return contents.encode("utf-8")

    def get_text_file(self, path, service, unit=None):
        """Return the content of a text file on the given unit."""
        unit_sentry = self._get_service_unit(service, unit=unit)
        return unit_sentry.file_contents(path)

    def get_landscape_config(self, unit=None):
        """Return a ConfigParser with service.conf data from the given unit."""
        config = ConfigParser()
        config.read_string(self.get_text_file(
            "/etc/landscape/service.conf", "landscape-server", unit=unit))
        return config

    def check_url(self, path, good_content, proto="https", post_data=None,
                  header=None, attempts=2, interval=5):
        """Polls the given path on the haproxy unit looking for good_content.

        If not found in the timeout period, will assert.  If found, returns
        the output matching.

        @param path: the path to poll
        @param good_content: string we are looking for, or list of strings
        @param proto: either https or http
        @param post_data: optional POST data string
        @param header: optional request header string
        @param interval: seconds two wait between attempts
        @param attempts: number of attempts to try
        """
        url = "%s://%s%s" % (proto, self.get_haproxy_public_address(), path)
        output = ""
        if type(good_content) is not list:
            good_content = [good_content]
        # XXX we should use pycurl here
        cmd = ["curl", url, "-k", "-L", "-s", "--compressed"]
        if post_data:
            cmd.extend(["-d", post_data])
        if header:
            cmd.extend(["-H", header])
        for _ in range(attempts):
            output = self._subprocess.check_output(cmd).decode("utf-8").strip()
            if all(content in output for content in good_content):
                return output
            sys.stdout.write(".")
            sys.stdout.flush()
            sleep(interval)
        msg = """Content Not found!
        url:{}
        good_content:{}
        output:{}
        """
        raise AssertionError(msg.format(url, good_content, output))

    def check_service(self, name, state="up", attempts=2, interval=5):
        """Check that a Landscape service is either up or down.

        @param name: The name of the Landscape service, excluding the
            "landscape-" prefix.
        @param state: Whether the service should be "up" or "down".
        @param attempts: Number of attempts to try.
        @param interval: Seconds two wait between attempts.
        """
        services = {
            "appserver": {
                "path": "/",
                "up": "passphrase",
                "down": "Landscape is unavailable"},
            "msgserver": {
                "path": "/message-system",
                "post_data": (
                    "ds8:messagesl;s22:next-expected-sequencei0;s8:"
                    "sequencei0;;"),
                "header": "X-MESSAGE-API: 3.1",
                "up": ["ds8:messagesl", "s11:server-uuid"],
                "down": "Landscape is unavailable"},
            "pingserver": {
                "path": "/ping",
                "protocol": "http",
                "up": "ds5:errors19:provide insecure_id;",
                "down": "Landscape is unavailable"},
            "api": {
                "path": "/api",
                "up": "Query API Service",
                "down": "Landscape is unavailable"},
            "package-upload": {
                "path": "/upload",
                "up": "package upload service",
                "down": "Landscape is unavailable"},
        }
        service = services[name]
        self.check_url(
            service["path"], service[state],
            proto=service.get("protocol", "https"),
            post_data=service.get("post_data"), header=service.get("header"),
            attempts=attempts, interval=interval)

    def pause_landscape(self, unit=None):
        """Execute the 'pause' action on a Landscape unit.

        The results of the action is returned.
        """
        unit = self._get_service_unit("landscape-server", unit=unit)
        action_id = self._do_action("pause", unit.info["unit_name"])
        return self._fetch_action(action_id)

    def resume_landscape(self, unit=None):
        """Execute the 'resume' action on a Landscape unit.

        The results of the action is returned.
        """
        unit = self._get_service_unit("landscape-server", unit=unit)
        action_id = self._do_action("resume", unit.info["unit_name"])
        return self._fetch_action(action_id)

    def bootstrap_landscape(self, admin_name, admin_email, admin_password,
                            unit=None):
        """Execute the 'bootstrap' action on a Landscape unit.

        The results of the action is returned.
        """
        unit = self._get_service_unit("landscape-server", unit=unit)
        bootstrap_params = {"admin-name": admin_name,
                            "admin-email": admin_email,
                            "admin-password": admin_password}
        action_id = self._do_action(
            "bootstrap", unit.info["unit_name"], bootstrap_params)
        return self._fetch_action(action_id)

    def wait_landscape_cron_jobs(self, unit=None):
        """Wait for running cron jobs to finish on the given Landscape unit."""
        unit = self._get_service_unit("landscape-server", unit=unit)
        output, code = unit.run(
            "sudo /opt/canonical/landscape/wait-batch-scripts")
        if code != 0:
            raise RuntimeError(output)

    def stop_landscape_service(self, service, unit=None, restore=True):
        """Stop the given service on the given Landscape unit.

        @param service: The service to stop.
        @param unit: The Landscape unit to act on.
        @param restore: Whether the service should be automatically restarted
            upon cleanUp.
        """
        self._control_landscape_service("stop", service, unit)
        if restore:
            self.addCleanup(self.start_landscape_service, service, unit=unit)

    def start_landscape_service(self, service, unit=None):
        """Start the given Landscape service on the given unit."""
        self._control_landscape_service("start", service, unit)

    def get_landscape_services_status(self, unit=None):
        """Return the status of the Landscape service on a Landscape unit.

        A dict is returned: {"running": [<list of running services],
                             "stopped": [<list of stopped sevices]}
        """
        unit = self._get_service_unit("landscape-server", unit=unit)
        output, _ = self._run("lsctl status", unit.info["unit_name"])
        service_status = {"running": [], "stopped": []}
        lines = output.splitlines()
        for line in lines:
            line = line.strip()
            if not line.startswith("* "):
                continue
            service_name = line[2:line.index(" is ")]
            if line.endswith("is not running"):
                service_status["stopped"].append(service_name)
            elif line.endswith("is running"):
                service_status["running"].append(service_name)
            else:
                raise AssertionError("Malformed status line: " + line)
        package_search_line = lines[-1]
        assert package_search_line.startswith("landscape-package-search"), (
            "Malformed status line: " + package_search_line)
        if "running" in package_search_line:
            service_status["running"].append(service_name)
        else:
            service_status["stopped"].append(service_name)
        return service_status

    def add_fake_db_patch(self, unit=None):
        """Add a fake DB patch to a landscape-server unit.

        A function which can be called to remove the DB patch to clean
        up is returned.
        """
        unit = self._get_service_unit("landscape-server", unit=unit)
        patch_dir = (
            "/opt/canonical/landscape/canonical/landscape/schema/patch_9999")
        unit.run("touch {}".format(patch_dir))
        return lambda: unit.run("rm -f {}".format(patch_dir))

    def configure_ssl(self, cert, key):
        """Start the given Landscape service on the given unit."""
        self._deployment.configure(
            "landscape-server", {"ssl-cert": cert, "ssl-key": key})
        self._wait_for_deployment_change_hooks()

    def set_unit_count(self, service, new_count):
        """Change the service to have the given number of units.

        If the existing service has fewer units than the new count, add
        units to the deployment.

        If the existing service has more units than the new count,
        arbitrary units are destroyed.
        """
        existing_units = sorted(
            unit_name for unit_name in self._deployment.sentry.unit.keys()
            if unit_name.startswith(service + "/"))
        current_count = len(existing_units)
        if current_count == new_count:
            return
        while current_count < new_count:
            self._deployment.add_unit(service)
            current_count += 1
        while current_count > new_count:
            self._deployment.destroy_unit(existing_units.pop())
            current_count -= 1
        self._wait_for_deployment_change_hooks()

    def destroy_landscape_leader(self):
        """Destroy the landscape-server leader

        This method will wait at most 60 seconds for a new leader to
        elected before returning.
        """
        leader, _ = self.get_unit_ids("landscape-server")
        self._deployment.destroy_unit("landscape-server/{}".format(leader))
        self._wait_for_deployment_change_hooks()
        for _ in range(60):
            leader, _ = self.get_unit_ids("landscape-server")
            if leader is not None:
                break
            time.sleep(1)
        assert leader is not None, "No new leader was elected."

    def get_unit_ids(self, service):
        """Return the numerical id parts for the units of the given service.

        A tuple with (leader, list_of_non_leaders) is returned.

        For example, if we have landscape-server/0 and
        landscape-server/1, where the first one is the leadder, (0, [1])
        is returned.
        """
        units = [
            unit for unit_name, unit in self._deployment.sentry.unit.items()
            if unit_name.startswith(service + "/")]
        leader = None
        non_leaders = []
        for unit in units:
            _, unit_number = unit.info["unit_name"].split("/")
            result, code = unit.run("is-leader --format=json")
            if json.loads(result):
                assert leader is None, "Multiple leaders found."
                leader = int(unit_number)
            else:
                non_leaders.append(int(unit_number))

        return leader, sorted(non_leaders)

    def _wait_for_deployment_change_hooks(self):
        """Wait for hooks to finish firing after a change in the deployment."""
        # Wait for initial landscape-server hooks to fire
        self._deployment.sentry.wait()
        # Wait for haproxy hooks to fire
        self._deployment.sentry.wait()
        # Wait for landscape-server hooks triggered by the haproxy ones to fire
        self._deployment.sentry.wait()

    def _run(self, command, unit):
        """Run a command on the given unit.

        The unicode stdout and stderr are returned as a tuple.
        """
        process = subprocess.Popen(
            ["juju", "run", "--unit", unit, command], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        return stdout.decode("utf-8"), stderr.decode("utf-8")

    def _do_action(self, action, unit, action_params=None):
        """Execute an action on a unit, returning the id."""
        command = ["juju", "action", "do", "--format=json", unit, action]
        if action_params is not None:
            sorted_action_params = sorted(
                action_params.items(), key=itemgetter(0))
            for key, value in sorted_action_params:
                if value is not None:
                    command.append("%s=%s" % (key, value))
        result = json.loads(
            self._subprocess.check_output(command).decode("utf-8"))
        return result["Action queued with id"]

    def _fetch_action(self, action_id, wait=300):
        """Fetch the results of an action."""
        return json.loads(self._subprocess.check_output(
            ["juju", "action", "fetch", "--format=json", "--wait", str(wait),
             action_id]).decode("utf-8"))

    def _get_charm_dir(self):
        """Get the path to the root of the charm directory."""
        return os.path.join(os.path.dirname(__file__), "..")

    def _get_sample_hashids_path(self):
        """Get the path to the flag file for enabling sample hashids."""
        return os.path.join(self._get_charm_dir(), "use-sample-hashids")

    def _get_bundle(self):
        """Return a dict with the data for the test bundle."""
        bundles_dir = os.path.join(self._get_charm_dir(), "bundles")
        environment = Environment(
            loader=FileSystemLoader(bundles_dir), trim_blocks=True,
            lstrip_blocks=True, keep_trailing_newline=True)
        context = DEFAULT_BUNDLE_CONTEXT.copy()

        # If we want an alternate PPA, let's add the relevant keys
        source = os.environ.get("LS_CHARM_SOURCE")
        if source:
            if source == "lds-trunk-ppa":
                # We want the lds-trunk PPA, let's grab its details from
                # the secrets directory
                secrets_dir = os.path.join(self._get_charm_dir(), "secrets")
                with open(os.path.join(secrets_dir, "lds-trunk-ppa")) as fd:
                    extra_config = yaml.safe_load(fd.read())
            else:
                extra_config = {
                    "source": source,
                    "key": os.environ.get("LS_CHARM_KEY", "4652B4E6")
                }
            context["landscape"].update(extra_config)

        # Add instance-specific configuration tweaks
        for service, options in self._config.items():
            context[service].update(options)

        template = environment.get_template("landscape-template.jinja2")
        return yaml.safe_load(template.render(context))

    def _build_repo_dir(self):
        """Create a temporary charm repository directory.

        XXX Apparently there's no way in Amulet to easily deploy uncommitted
            changes, so we create a temporary charm repository with a symlink
            to the branch.
        """
        config = self._deployment.services["landscape-server"]
        config["charm"] = "local:trusty/landscape-server"
        branch_dir = config.pop("branch")
        repo_dir = tempfile.mkdtemp()
        series_dir = os.path.join(repo_dir, self._series)
        os.mkdir(series_dir)
        charm_link = os.path.join(series_dir, "landscape-server")
        os.symlink(branch_dir, charm_link)
        os.environ["JUJU_REPOSITORY"] = repo_dir

        # Enable sample hashids
        with open(self._get_sample_hashids_path(), "w") as fd:
            fd.write("")

        return repo_dir

    def _clean_repo_dir(self, repo_dir):
        """Clean up the repository directory and the sample hashids flag."""
        shutil.rmtree(repo_dir)
        os.unlink(self._get_sample_hashids_path())

    def _control_landscape_service(self, action, service, unit=None):
        """Start or stop the given Landscape service on the given unit."""
        unit = self._get_service_unit("landscape-server", unit=unit)
        output, code = unit.run("sudo service %s %s" % (service, action))
        if code != 0:
            raise RuntimeError(output)

    def _get_service_unit(self, service, unit=None):
        """Get the given unit for the specified service.

        @param service: The name of the Juju service
        @param unit: The id of the unit within the service. If None is
            provided, it's assumed that the service has only one unit, which
            will be returned. Passing in None if the service has more
            than one unit will cause an error. (The rational is that if
            there are more than one unit, you should be aware of it)

        E.g., _get_service_unit("landscape-server", 5) will return the
        landscape-server/5 unit.
        """
        if unit is not None:
            unit_name = "{}/{}".format(service, unit)
            unit = self._deployment.sentry.unit["landscape-server/%d" % unit]
        else:
            [unit_name] = [
                unit_name for unit_name in self._deployment.sentry.unit.keys()
                if unit_name.startswith("{}/".format(service))]
        return self._deployment.sentry.unit[unit_name]


class IntegrationTest(TestWithFixtures):
    """Charm integration tests.

    Sub-classes are expected to set the layer they want to get the setup of.
    """

    layer = None  # Must be set by sub-classes

    maxDiff = None

    @property
    def environment(self):
        """Convenience for getting the EnvironmentFixture of the layer."""
        return self.layer.environment


def main(config=None):
    """Run all relevant integration tests for this file.

    @param config: A dict with configuration tweaks, so the initial layer can
        be brought up using a custom landscape-server charm configuration.
    """
    global _config
    _config = config

    # XXX This will force zope.testrunner to write to stderr, since stdout is
    # not being printed synchronously by "juju test", see also the call to
    # subprocess in charmtools.test.Orchestra.perform().
    sys.stdout = sys.stderr

    # Figure out the package holding the test files to use and run them.
    path = os.path.join(os.getcwd(), "tests")
    module = os.path.basename(sys.argv[0]).split("-")[1]
    args = sys.argv[:]
    args.extend(["-vv", "--path", path, "--tests-pattern", "^%s$" % module])
    run(args=args)


def get_config():
    return _config


def get_ssl_certificate_over_wire(endpoint):
    """Return the SSL certificate used at the given endpoint.

    @param endpoint: An SSL endpoint in the form <host:port>.
    """
    # Call openssl s_client connect to get the actual certificate served.
    # The command line program is a bit archaic and therefore we need
    # to do a few things like send it a newline char (a user "return"), and
    # filter some of the output (it print non-error messages on stderr).
    process = subprocess.Popen(('echo', '-n'), stdout=subprocess.PIPE)
    with open(os.devnull, 'w') as dev_null:
        output = subprocess.check_output(  # output is bytes
            ['openssl', 's_client', '-connect', endpoint],
            stdin=process.stdout, stderr=dev_null)
    process.stdout.close()  # Close the pipe fd
    process.wait()  # This closes the subprocess sending the newline.

    # A regex might be nicer, but this works and is easy to read.
    certificate = output.decode("utf-8")
    start = certificate.find("-----BEGIN CERTIFICATE-----")
    end = certificate.find("-----END CERTIFICATE-----") + len(
        "-----END CERTIFICATE-----")
    return certificate[start:end]


# Global environment configuration
_config = None
