"""
Common helpers for landscpae integration tests.
"""

import json
import logging
import unittest
import sys
import yaml
import os
import subprocess

from os import getenv
from os.path import splitext, basename
from subprocess import CalledProcessError, check_output, PIPE
from time import sleep

from fixtures import Fixture

from amulet import Deployment

from jinja2 import FileSystemLoader, Environment

log = logging.getLogger(__file__)

# Default values for rendering the bundle jinja2 template
DEFAULT_BUNDLE_CONTEXT = {
    "name": "test",
    "rabbitmq": {},
    "postgresql": {
        "max_connections": 100,
        "memory": 128,
        "manual_tuning": True,
        "shared_buffers": "32MB"},
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

    _timeout = 1500
    _series = "trusty"
    _deployment = Deployment()

    def __init__(self, config=None):
        """
        @param config: Optionally a dict with extra bundle template context
            values. It will be merged into DEFAULT_BUNDLE_CONTEXT when
            deploying the test bundle.
        """
        self._config = config or {}

    def setUp(self):
        super(EnvironmentFixture, self).setUp()
        if not self._deployment.deployed:
            self._deployment.load(self._get_bundle())
            self._deployment.setup(timeout=self._timeout)
            self._deployment.sentry.wait(self._timeout)

    def get_haproxy_public_address(self, unit=0):
        """Return the public address of the given haproxy unit."""
        unit = self._deployment.sentry.unit["haproxy/%d" % unit]
        return unit.info["public-address"]

    def stop_landscape_service(self, service, unit=0):
        """Stop the given Landscape service on the given unit."""
        self._control_landscape_service("stop", service, unit)

    def start_landscape_service(self, service, unit=0):
        """Start the given Landscape service on the given unit."""
        self._control_landscape_service("start", service, unit)

    def _get_bundle(self):
        """Return a dict with the data for the test bundle."""
        charm_dir = os.path.join(os.path.dirname(__file__), "..")
        bundles_dir = os.path.join(charm_dir, "bundles")
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
                secrets_dir = os.path.join(charm_dir, "secrets")
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

    def _control_landscape_service(self, action, service, unit):
        """Start or stop the given Landscape service on the given unit."""
        unit = self._deployment.sentry.unit["landscape-server/%d" % unit]
        output, code = unit.run("sudo service %s %s" % (service, action))
        if code != 0:
            raise RuntimeError(output)


@unittest.skipIf(
    getenv("SKIP_TESTS", None), "Requested to skip all tests.")
class BaseLandscapeTests(unittest.TestCase):
    """
    Base class with some commonality between all test classes.
    """

    maxDiff = None

    def __str__(self):
        file_name = splitext(basename(__file__))[0]
        return "{} ({}.{})".format(
            self._testMethodName, file_name, self.__class__.__name__)


def get_ssl_certificate(endpoint):
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


def check_url(url, good_content, post_data=None, header=None,
              interval=5, attempts=2, retry_unavailable=False):
    """
    Polls the given URL looking for the specified good_content.  If
    not found in the timeout period, will assert.  If found, returns
    the output matching.

    @param url: URL to poll
    @param good_content: string we are looking for, or list of strings
    @param post_data: optional POST data string
    @param header: optional request header string
    @param interval: number of seconds between polls
    @param attempts: how many times we should poll
    @param retry_unavailable: if host is unavailable, retry (default: False)
    """
    output = ""
    if type(good_content) is not list:
        good_content = [good_content]
    cmd = ["curl", url, "-k", "-L", "-s", "--compressed"]
    if post_data:
        cmd.extend(["-d", post_data])
    if header:
        cmd.extend(["-H", header])
    for _ in range(attempts):
        try:
            output = check_output(cmd).decode("utf-8").strip()
        except CalledProcessError as e:
            if not retry_unavailable:
                raise
            status = e.returncode
            # curl: rc=7, host is unavailable, this can happen
            #       when apache is being restarted, for instance
            if status == 7:
                log.info("Unavailable, retrying: {}".format(url))
            else:
                raise
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


def juju_status():
    """Return a juju status structure."""
    cmd = ["juju", "status", "--format=json"]
    output = check_output(cmd).decode("utf-8").strip()
    return json.loads(output)


def get_service_config(service_name):
    """
    Returns the configuration of the given service. Raises an error if
    the service is not there.

    @param juju_status: dictionary representing the juju status output.
    @param service_name: string representing the service we are looking for.
    """
    cmd = ["juju", "get", "--format=yaml", service_name]
    output = check_output(cmd).decode("utf-8").strip()
    return yaml.load(output)


def find_address(juju_status, service_name):
    """
    Find the first unit of service_name in the given juju status dictionary.
    Doesn't handle subordinates, sorry.

    @param juju_status: dictionary representing the juju status output.
    @param service_name: String representing the name of the service.
    """
    services = juju_status["services"]
    if service_name not in services:
        raise ServiceOrUnitNotFound(service_name)
    service = services[service_name]
    units = service.get("units", {})
    unit_keys = list(sorted(units.keys()))
    if unit_keys:
        public_address = units[unit_keys[0]].get("public-address", "")
        return public_address
    else:
        raise ServiceOrUnitNotFound(service_name)


def get_landscape_units(juju_status):
    """
    Return a list of all the landscape service units.

    @param juju_status: dictionary representing the juju status output.
    """
    landscape_units = []
    services = juju_status["services"]
    for service_name in services:
        if not service_name.startswith("landscape"):
            continue
        service = services[service_name]
        units = service.get("units", {})
        unit_keys = list(sorted(units.keys()))
        if unit_keys:
            landscape_units.extend(unit_keys)
    if not landscape_units:
        raise ServiceOrUnitNotFound("landscape")
    return landscape_units


def get_landscape_service_conf(unit):
    """Fetch the contents of service.conf from the given unit."""
    cmd = ["juju", "ssh", unit, "sudo cat /etc/landscape/service.conf "
           "2>/dev/null"]
    output = check_output(cmd, stderr=PIPE).decode("utf-8").strip()
    return output


def run_command_on_unit(cmd, unit):
    """Run the given command on the given unit and return the output."""
    output = check_output(["juju", "ssh", unit, cmd], stderr=PIPE)
    return output.decode("utf-8").strip()


class ServiceOrUnitNotFound(Exception):
    """
    Exception thrown if a service cannot be found in the deployment or has
    no units.
    """

    def __init__(self, service_name):
        self.service_name = service_name
