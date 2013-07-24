#!/usr/bin/env python
"""
hooks.py - entrypoint script for all landscape hooks
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from lib import util
from lib.juju import Juju

import os
import sys
import yaml
import shutil
import re
import pycurl
import cStringIO
import psutil
from subprocess import (check_call, check_output)
from ConfigParser import RawConfigParser


def _download_file(url):
    """ Download from a url and save to the filename given """
    buf = cStringIO.StringIO()
    juju.juju_log("Fetching License: %s" % url)
    curl = pycurl.Curl()
    curl.setopt(pycurl.URL, str(url))
    curl.setopt(pycurl.WRITEFUNCTION, buf.write)
    curl.perform()
    curl.close()
    return buf.getvalue()

def _a2enmod(modules):
    for module in modules:
        check_call(["a2enmod", module])

def _a2dissite(site):
    check_call(["a2dissite", site])

def _a2ensite(site):
    check_call(["a2ensite", site])

def _service(service, action):
    check_call(["service", service, action])

def _setup_apache():
    """
    Setup apache2 to serve static landscape content
    """
    public = juju.unit_get("public-address")
    _a2enmod(["rewrite", "proxy_http", "ssl", "headers", "expires"])
    _a2dissite("default")
    shutil.copy("%s/hooks/conf/landscape-http" % ROOT, LANDSCAPE_APACHE_SITE)
    _replace_in_file(LANDSCAPE_APACHE_SITE, r"@hostname@", public)
    _a2ensite("landscape")
    _service("apache2", "restart")

def _install_license():
    """
    Read the license from the config.  It can either be just the data
    as plain text, or it can be a URL.  In either case, save it to the
    global LANDSCAPE_LICENSE_DEST
    """
    license_file_re = r"^(file://|http://|https://).*$"
    license_file = juju.config_get("license-file")
    if license_file == "":
        juju.juju_log("license file not set, skipping")
        return
    if re.match(license_file_re, license_file):
        license_file = _download_file(license_file)

    with open(LANDSCAPE_LICENSE_DEST, 'wb') as fp:
        fp.write(license_file)

def _replace_in_file(filename, regex, replacement):
    """
    Operate on a file like sed.
    @param file - filename of file to operate on
    @param regex - regular expression to pass to re.sub() eg:. r'^foo'
    @param replacement - replacement text to substitute over the matched regex
    """
    with open(filename, "r") as default:
        lines = default.readlines()
    with open(filename, "w") as default:
        for line in lines:
            default.write(re.sub(regex, replacement, line))

def _get_system_numcpu():
    """ Return the number of cores on the system """
    return psutil.NUM_CPUS

def _get_system_ram():
    """ Return the system ram in Gigabytes """
    return psutil.phymem_usage()[0] / (1024 ** 3)

def _calc_daemon_count(service, minimum=1, auto_maximum=None, maximum=None,
        requested=None):
    """
    Calculate the appropriate number of daemons to spawn for a requested
    service.

    @param service name of the service
    @param minimum minimum number of daemons to spawn
    @param auto_maximum maximum number of daemons to spawn with the AUTO
        setting (None == 1024)
    @param maximum maximum number of daemons to spawn (None == 1024)
    @param requested The user requested number, if formatted correctly > 0,
       it wins (up to max)
    """
    if auto_maximum is None:
        auto_maximum = 1024
    if maximum is None:
        maximum = 1024
    if requested is not None:
        if re.match(r'\d+', requested) and int(requested) > 0:
            return min(requested, maximum)
    ram = _get_system_ram()
    numcpu = _get_system_numcpu()
    numdaemons = 1 + numcpu + ram - 2
    return max(minimum, min(auto_maximum, numdaemons))

def _get_requested_service_count():
    """
    Parse and return the requested service count as a dict,
    anything not set, default it to AUTO here.  Expected settings:

    - AUTO = all services default to AUTO
    - <integer> = all services default requested to be this
    - <service_name>:<integer> = service_name defaults to number set
    - <service_name>:AUTO = service_name defaults to AUTO
    """
    result = {}
    service_counts = juju.config_get("service-count").split()
    if len(service_counts) == 1:
        if re.match(r'^\d+$', service_counts[0]):
            for service in SERVICE_COUNT:
                result[service] = service_counts[0]
            return result
    for service_count in service_counts:
        count = service_count
        if re.match(r'^.*:\d+$', service_count):
            (service, count) = service_count.split(":")
            result[service] = count 
    for service in SERVICE_COUNT:
        if service not in result:
            result[service] = "AUTO"
    return result

def _get_services_dict():
    """
    Parse the services and service-count config setting, and return how many
    of each service should actually be started.  If setting is 'AUTO' we will
    try to guess the number for the user.  If the setting is not understood
    in some manner, assume it to be AUTO
    """
    result = {}
    requested = _get_requested_service_count()

    # First, set all requested services to run
    for service in _get_requested_services():
        args = [service]
        args.extend(SERVICE_COUNT[service][1:])
        args.append(requested[service])
        result[service] = SERVICE_COUNT[service][0](*args)
    return result

def _enable_services():
    """
    Enabled services requested by user through services and service-count
    config settings.
    """
    services = _get_services_dict()
    juju.juju_log("Selected Services: %s" % services.keys())
    for service in services:
        juju.juju_log("Enabling: %s" % service)
        if service == "static":
            _setup_apache()
        else:
            var = SERVICE_DEFAULT[service]
            _replace_in_file(LANDSCAPE_DEFAULT_FILE,
                             r"^%s=.*$" % var,
                             "%s=%s" % (var, services[service]))

def _format_service(name, port=None, httpchk="GET / HTTP/1.0",
        server_options="check inter 2000 rise 2 fall 5 maxconn 50",
        service_options=None):
    """
    Given a name and port, define a service in python data-structure
    format that will be exported as a yaml config to be set int a
    relation variable.  Override options by altering the SERVICE
    hash aboe.

    @param name Name of the service (letters, numbers, underscores)
    @param port Port this service will be running on
    @param server_options override the server_options (String)
    @param httpchk The httpchk option, will be appeneded to service_options
    @param service_options override the service_options (Array of strings)
    """
    if service_options is None:
        service_options = ["mode http", "balance leastconn"]
    if httpchk is not None:
        httpchk_option = "option httpchk %s" % httpchk
        service_options.append(httpchk_option)

    host = juju.unit_get("private-address")
    result = {
        "service_name": name, 
        "service_options": service_options,
        "servers": [[name, host, port, server_options]]}
    return result

def _get_requested_services():
    result = []
    config = juju.config_get()
    if "services" in config:
        for service in config["services"].split():
            if service not in SERVICE_DEFAULT:
                juju.juju_log("Invalid Service: %s" % service)
                raise Exception("Invalid Service: %s" % service)
            result.append(service)
    return result

def _get_services_haproxy():
    """
    Get the services that were configured to run.  Return in a format
    understood by haproxy.
    """
    result = []
    for service in _get_requested_services():
        juju.juju_log("service: %s" % service)
        result.append(_format_service(service, **SERVICE_PROXY[service]))
    return result

def _lsctl_restart():
    check_call(["lsctl", "restart"])

def website_relation_joined():
    host = juju.unit_get("private-address")
    # N.B.: Port setting necessary due to limitations with haproxy charm
    juju.relation_set(
            services=yaml.safe_dump(_get_services_haproxy()),
            hostname=host, port=80)

def db_admin_relation_joined():
    pass

def db_admin_relation_changed():
    host = check_output(["relation-get", "host"]).strip()
    admin = check_output(["relation-get", "user"]).strip()
    admin_password = check_output(["relation-get", "password"]).strip()
    allowed_units = check_output(["relation-get", "allowed-units"]).strip()
    unit_name = os.environ['JUJU_UNIT_NAME']
    user = "landscape"
    password = "landscape"

    if not host or not admin or not admin_password:
        juju.juju_log("Need host, user and password in relation"
            " before proceeding")
        return

    if not allowed_units or unit_name not in allowed_units:
        juju.juju_log("%s not in allowed_units yet (%s)" % (
            unit_name, allowed_units))
        return

    config_file = "/etc/landscape/service.conf"
    parser = RawConfigParser()
    parser.read([config_file])
    parser.set("stores", "host", host)
    parser.set("stores", "port", "5432")
    parser.set("stores", "user", user)
    parser.set("stores", "password", password)
    parser.set("schema", "store_user", admin)
    parser.set("schema", "store_password", admin_password)
    with open(config_file, "w+") as output_file:
        parser.write(output_file)

    # Create the inital landscape user (to have a known password)
    util.create_user(host, admin, admin_password, user, password)

    # Setup the landscape server and restart services.  The method
    # is smart enough to skip if nothing needs to be done, and 
    # protect against concurrent access to the database.
    util.setup_landscape_server(host, admin, admin_password)
    check_call(["lsctl", "restart"])

def amqp_relation_joined():
    juju.relation_set("username=landscape")
    juju.relation_set("vhost=landscape")

def amqp_relation_changed():
    password = check_output(["relation-get", "password"]).strip()
    host = check_output(["relation-get", "hostname"]).strip()

    juju.juju_log("Using AMPQ server at %s" % host)

    if password == "":
        sys.exit(0)

    config_file = "/etc/landscape/service.conf"

    parser = RawConfigParser()
    parser.read([config_file])

    parser.set("broker", "password", password)
    parser.set("broker", "host", host)
    parser.set("broker", "user", "landscape")

    with open(config_file, "w+") as output_file:
        parser.write(output_file)


def config_changed():
    _install_license()
    _lsctl_restart()
    _enable_services()

SERVICE_PROXY = {
        "static": {"port": "80"},
        "appserver": {"port": "8080"},
        "msgserver": {
            "port": "8090", "httpchk": "HEAD /index.html HTTP/1.0"},
        "pingserver": {
            "port": "8070", "httpchk": "HEAD /ping HTTP/1.0"},
        "combo-loader": {
            "port": "9070",
            "httpchk": "HEAD /?yui/scrollview/scrollview-min.js HTTP/1.0"},
        "async-frontend": {"port": "9090"},
        "apiserver": {"port": "9080"},
        "package-upload": {"port": "9100"},
        "package-search": {"port": "9090"}}

# Fomrat is:
#   [method, min, auto_max, real_max]
#   method = method to use to determine what the count should be
#   min = minimum number of daemons to launch
#   auto_max = if auto-determining, only suggest this as the max
#   real_max = hard-cutoff, cannot launch more than this.
SERVICE_COUNT = {
        "appserver": [_calc_daemon_count, 1, 4, None],
        "msgserver": [_calc_daemon_count, 2, 16, None],
        "pingserver": [_calc_daemon_count, 1, 16, None],
        "combo-loader": [_calc_daemon_count, 1, 2, None],
        "async-frontend": [_calc_daemon_count, 1, 2, None],
        "apiserver": [_calc_daemon_count, 1, 2, None],
        "jobhandler": [_calc_daemon_count, 1, 2, None],
        "package-upload": [_calc_daemon_count, 1, 1, 1],
        "package-search": [_calc_daemon_count, 1, 1, 1],
        "juju-sync": [_calc_daemon_count, 1, 1, 1],
        "cron": [_calc_daemon_count, 1, 1, 1],
        "static": [_calc_daemon_count, 1, 1, 1]}
        

SERVICE_DEFAULT = {
        "appserver": "RUN_APPSERVER",         
        "msgserver": "RUN_MSGSERVER",
        "pingserver": "RUN_PINGSERVER",
        "combo-loader": "RUN_COMBO_LOADER",
        "async-frontend": "RUN_ASYNC_FRONTEND",
        "apiserver": "RUN_APISERVER",
        "package-upload": "RUN_PACKAGEUPLOADSERVER",
        "jobhandler": "RUN_JOBHANDLER",
        "package-search": "RUN_PACKAGESEARCH",
        "juju-sync": "RUN_JUJU_SYNC",
        "cron": "RUN_CRON",
        "static": None}

LANDSCAPE_DEFAULT_FILE = "/etc/default/landscape-server"
LANDSCAPE_APACHE_SITE = "/etc/apache2/sites-available/landscape"
LANDSCAPE_LICENSE_DEST = "/etc/landscape/license.txt"
ROOT = os.path.abspath(os.path.curdir)
juju = Juju()

if __name__ == "__main__":
    hooks = {
        "config-changed": config_changed,
        "amqp-relation-joined": amqp_relation_joined,
        "amqp-relation-changed": amqp_relation_changed,
        "db-admin-relation-joined": db_admin_relation_joined,
        "db-admin-relation-changed": db_admin_relation_changed,
        "website-relation-joined": website_relation_joined}
    hook = os.path.basename(sys.argv[0])
    # If the hook is unsupported, let it raise a KeyError and exit with error.
    hooks[hook]()
