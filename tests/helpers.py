"""
Common helpers for landscpae integration tests.
"""

import json
import logging
import unittest
import sys
import yaml

from os import getenv
from os.path import splitext, basename
from subprocess import CalledProcessError, check_output, PIPE

from time import sleep

log = logging.getLogger(__file__)


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
