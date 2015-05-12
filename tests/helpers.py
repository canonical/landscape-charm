"""
Common helpers for landscpae integration tests.
"""

import json
import logging
import sys
import yaml
import os
import subprocess
import tempfile
import shutil

from os import getenv
from subprocess import CalledProcessError, check_output, PIPE
from time import sleep

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

    def __init__(self, config=None, deployment=None):
        """
        @param config: Optionally a dict with extra bundle template context
            values. It will be merged into DEFAULT_BUNDLE_CONTEXT when
            deploying the test bundle.
        """
        self._config = config or {}
        if deployment is not None:
            self._deployment = deployment

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

        self._stopped_landscape_services = []
        self.addCleanup(self._restore_stopped_landscape_services)

    def get_haproxy_public_address(self, unit=0):
        """Return the public address of the given haproxy unit."""
        unit = self._deployment.sentry.unit["haproxy/%d" % unit]
        return unit.info["public-address"]

    def stop_landscape_service(self, service, unit=0):
        """Stop the given Landscape service on the given unit.

        The service being stopped will be automatically restarted upon cleanUp.
        """
        self._control_landscape_service("stop", service, unit)
        self._stopped_landscape_services.append((service, unit))

    def start_landscape_service(self, service, unit=0):
        """Start the given Landscape service on the given unit."""
        self._control_landscape_service("start", service, unit)

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

    def _control_landscape_service(self, action, service, unit):
        """Start or stop the given Landscape service on the given unit."""
        unit = self._deployment.sentry.unit["landscape-server/%d" % unit]
        output, code = unit.run("sudo service %s %s" % (service, action))
        if code != 0:
            raise RuntimeError(output)

    def _restore_stopped_landscape_services(self):
        """Automatically restore any service that was stopped."""
        for service, unit in self._stopped_landscape_services:
            self.start_landscape_service(service, unit=unit)


class OneLandscapeUnitLayer(object):

    config = None

    @classmethod
    def setUp(cls):
        cls.environment = EnvironmentFixture(config=cls.config)
        cls.environment.setUp()

    @classmethod
    def tearDown(cls):
        cls.environment.cleanUp()


class IntegrationTest(TestWithFixtures):
    """Host all the tests to run against a minimal Landscape deployment.

    The deployment will have one unit of each needed service, with default
    configuration.
    """
    layer = OneLandscapeUnitLayer

    def setUp(self):
        super(IntegrationTest, self).setUp()
        self.environment = self.layer.environment


def main(config=None):
    OneLandscapeUnitLayer.config = config

    # Figure out the package holding the test files to use and run them.
    path = os.path.join(os.getcwd(), "tests")
    module = os.path.basename(sys.argv[0]).split("-")[1]
    args = sys.argv[:]
    args.extend(["-vv", "--path", path, "--tests-pattern", "^%s$" % module])
    run(args=args)


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
