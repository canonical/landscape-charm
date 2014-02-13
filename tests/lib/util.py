#!/usr/bin/python2.7

import amulet
from base64 import b64encode
from deployer.config import ConfigStack
from deployer.utils import resolve_include
from subprocess import check_output


def _resolve_include(value):
    """
    resolve include-*:// style links in the way that
    juju-deployer does.  I cut and paste this code for now
    since it was a bit burried in a method.  The goal is
    to move this into amulet, I really don't want to maintain
    this here.
    """
    for include_type in ["file", "base64"]:
        if (not isinstance(value, str)
            or not value.startswith(
                "include-%s://" % include_type)):
            continue
        include, fname = value.split("://", 1)
        include_path = resolve_include(fname, ".")
        with open(include_path) as fh:
            result = fh.read()
            if include_type == "base64":
                result = b64encode(result)
            return result
    return value

def load_deployer_config(yaml_file):
    """
    return a deployer config file in a format that amulet expects
    """
    config = ConfigStack([yaml_file])
    config.load()
    deployment = config.get("landscape")
    data = deployment.data
    if "relations" not in data:
        data["relations"] = {}
    for service_name, service in data["services"].iteritems():
        if "options" in service:
            for key, value in service["options"].items():
                service["options"][key] = _resolve_include(value)
                # FIXME: This is only needed since amulet switches your environment
                #        if you pass in a config.  There are ways to break this
                #        parsing (like including a quote in your environment name).
    output = check_output(['juju', 'env']).strip()
    if output.startswith("Current environment: "):
    # Current environment: "andreas-canonistack2" (from JUJU_ENV)
        # <= Juju 1.16
        environment_name = output.split()[2].strip('"')
    else:
        environment_name = output
    return {environment_name: data}


