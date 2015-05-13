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

from os import getenv
from subprocess import check_output
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

    def get_haproxy_certificate(self, unit=0):
        """Return the certificate that haproxy is using for SSL termination."""
        endpoint = "%s:443" % self.get_haproxy_public_address()
        return _get_ssl_certificate(endpoint)

    def get_ssl_certificate(self, unit=0):
        """Return SSL certificate set on the given Landscape unit."""
        unit = self._deployment.sentry.unit["landscape-server/%d" % unit]
        return unit.file_contents("/etc/ssl/certs/landscape_server_ca.crt")

    def get_config(self, unit=0):
        """Return a ConfigParser with service.conf data from the given unit."""
        unit = self._deployment.sentry.unit["landscape-server/%d" % unit]
        content = unit.file_contents("/etc/landscape/service.conf")
        config = ConfigParser()
        config.read_string(content)
        return config

    def check_url(self, path, good_content, proto="https", post_data=None,
                  header=None):
        """Polls the given path on the haproxy unit looking for good_content.

        If not found in the timeout period, will assert.  If found, returns
        the output matching.

        @param path: The path to poll
        @param good_content: string we are looking for, or list of strings
        @param proto: Either https or http
        @param post_data: optional POST data string
        @param header: optional request header string
        """
        interval = 5
        attempts = 2

        url = "%s://%s%s" % (proto, self.get_haproxy_public_address(), path)
        output = ""
        if type(good_content) is not list:
            good_content = [good_content]
        cmd = ["curl", url, "-k", "-L", "-s", "--compressed"]
        if post_data:
            cmd.extend(["-d", post_data])
        if header:
            cmd.extend(["-H", header])
        for _ in range(attempts):
            output = check_output(cmd).decode("utf-8").strip()
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
    """Layer for all tests meant to run against a minimal Landscape deployment.

    The deployment will have one unit of each needed service, with default
    configuration.
    """

    config = None

    @classmethod
    def setUp(cls):
        cls.environment = EnvironmentFixture(config=cls.config)
        cls.environment.setUp()

    @classmethod
    def tearDown(cls):
        cls.environment.cleanUp()


class IntegrationTest(TestWithFixtures):
    """Charm integration tests.

    Sub-classes are expected to set the layer they want to get the setup of.
    """

    layer = None  # Must be set by sub-classes

    @property
    def environment(self):
        """Convenience for getting the EnvironmentFixture of the layer."""
        return self.layer.environment


def main(config=None):
    """Run all relevant integration tests for this file.

    @param config: A dict with configuration tweaks, so the initial layer can
        be brought up using a custom landscape-server charm configuration.
    """
    OneLandscapeUnitLayer.config = config

    # Figure out the package holding the test files to use and run them.
    path = os.path.join(os.getcwd(), "tests")
    module = os.path.basename(sys.argv[0]).split("-")[1]
    args = sys.argv[:]
    args.extend(["-vv", "--path", path, "--tests-pattern", "^%s$" % module])
    run(args=args)


def _get_ssl_certificate(endpoint):
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
