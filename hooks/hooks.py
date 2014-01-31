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
import datetime
import psycopg2
from copy import deepcopy
from base64 import b64encode
from subprocess import check_call
from ConfigParser import RawConfigParser, Error


def website_relation_joined():
    host = juju.unit_get("private-address")
    # N.B.: Port setting necessary due to limitations with haproxy charm
    juju.relation_set(
            services=yaml.safe_dump(_get_services_haproxy()),
            hostname=host, port=80)


def notify_website_relation():
    """
    Notify the website relation of changes to the services.  Juju optimizes
    duplicate values out of this, so we don't need to worry about calling it
    only in case of a change
    """
    juju.juju_log(yaml.safe_dump(_get_services_haproxy()))
    for id in juju.relation_ids("website"):
        juju.relation_set(
            relation_id=id,
            services=yaml.safe_dump(_get_services_haproxy()))


def db_admin_relation_joined():
    pass


def db_admin_relation_changed():
    host = juju.relation_get("host")
    admin = juju.relation_get("user")
    admin_password = juju.relation_get("password")
    allowed_units = juju.relation_get("allowed-units")
    remote_state = juju.relation_get("state")
    unit_name = juju.local_unit()

    user = "landscape"
    password = juju.config_get("landscape-password")

    if not host or not admin or not admin_password:
        juju.juju_log("Need host, user and password in relation"
            " before proceeding")
        return

    if not allowed_units or unit_name not in allowed_units:
        juju.juju_log("%s not in allowed_units yet (%s)" % (
            unit_name, allowed_units))
        return

    # Cluster aware: Ignore standby, failover and transition states
    ignored_states = set(["hot standby", "failover"])
    relation_count = len(juju.relation_list())
    if relation_count > 1:
        juju.juju_log(
            "Our database is clustered with %s units."
            "Ignoring any intermittent 'standalone' states."
            % relation_count)
        ignored_states.add("standalone")

    if remote_state is None or remote_state in ignored_states:
        juju.juju_log(
            "No config changes made. Invalid state '%s' for host %s." %
            (remote_state, host))
        return

    juju.juju_log("Updating config due to database changes.")

    parser = RawConfigParser()
    parser.read([LANDSCAPE_SERVICE_CONF])
    parser.set("stores", "host", host)
    parser.set("stores", "port", "5432")
    parser.set("stores", "user", user)
    parser.set("stores", "password", password)
    parser.set("schema", "store_user", admin)
    parser.set("schema", "store_password", admin_password)

    # Write new changes to LANDSCAPE_NEW_SERVICE_CONF to test first
    with open(LANDSCAPE_NEW_SERVICE_CONF, "w") as output_file:
        parser.write(output_file)

    if not util.is_db_up("postgres", host, admin, admin_password):
        juju.juju_log(
            "Ignoring config changes. Because new service settings don't "
            "have proper permissions setup on the host %s." % host)
        return

    # Changes are validated; db is up has write-accessible
    with open(LANDSCAPE_SERVICE_CONF, "w+") as output_file:
        parser.write(output_file)

    try:
        conn = util.connect_exclusive(host, admin, admin_password)
    except psycopg2.Error:
        # Another unit is performing database configuration.
        pass
    else:
        try:
            util.create_user(conn, user, password)
            check_call("setup-landscape-server")
        finally:
            conn.close()

    try:
        # Handle remove-relation db-admin.  This call will fail because
        # database access has already been removed.
        config_changed()  # only restart if is_db_up and _is_amqp_up
    except Exception as e:
        juju.juju_log(str(e), level="DEBUG")


def amqp_relation_joined():
    juju.relation_set("username=landscape")
    juju.relation_set("vhost=landscape")


def _is_amqp_up():
    """Return C{True} if the ampq-relation has defined required values"""
    relid = juju.relation_ids("amqp")[0]         # TODO support amqp clusters?
    amqp_unit = juju.relation_list(relid)[0]     # TODO support amqp clusters?

    host = juju.relation_get(
        "hostname", unit_name=amqp_unit, relation_id=relid)
    password = juju.relation_get(
        "password", unit_name=amqp_unit, relation_id=relid)
    if None in [host, password]:
        juju.juju_log(
            "Waiting for valid hostname/password values from amqp relation")
        return False
    return True


def amqp_relation_changed():
    if not _is_amqp_up():
        sys.exit(0)

    password = juju.relation_get("password")
    host = juju.relation_get("hostname")

    juju.juju_log("Using AMPQ server at %s" % host)

    parser = RawConfigParser()
    parser.read([LANDSCAPE_SERVICE_CONF])

    parser.set("broker", "password", password)
    parser.set("broker", "host", host)
    parser.set("broker", "user", "landscape")

    with open(LANDSCAPE_SERVICE_CONF, "w+") as output_file:
        parser.write(output_file)

    if _is_db_up():
        config_changed()  # only restarty is_db_up and _is_amqp_up


def config_changed():
    _lsctl("stop")
    _install_license()
    _enable_services()
    _set_maintenance()
    _set_upgrade_schema()

    if _is_db_up() and _is_amqp_up():
        _lsctl("start")

    notify_website_relation()


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


def _a2enmods(modules):
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
    _a2enmods(["rewrite", "proxy_http", "ssl", "headers", "expires"])
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

    with open(LANDSCAPE_LICENSE_DEST, "wb") as fp:
        fp.write(license_file)


def _replace_in_file(filename, regex, replacement):
    """
    Operate on a file like sed.
    @param file - filename of file to operate on
    @param regex - regular expression to pass to re.sub() eg:. r"^foo"
    @param replacement - replacement text to substitute over the matched regex
    """
    juju.juju_log("Setting in file %s: %s" % (filename, replacement))
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
        setting (None == 9)
    @param maximum maximum number of daemons to spawn (None == 9)
    @param requested The user requested value (String), if formatted
       correctly > 0, it wins (up to maximum)
    """
    # The "9" limitation is hardcoded in landcape init scripts right now
    if auto_maximum is None:
        auto_maximum = 9
    if maximum is None:
        maximum = 9
    if requested is not None:
        if re.match(r"\d+", requested) and int(requested) > 0:
            return min(int(requested), maximum)
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
        if re.match(r"^\d+$", service_counts[0]):
            return dict.fromkeys(SERVICE_COUNT, service_counts[0])
    result = dict.fromkeys(SERVICE_COUNT, "AUTO")
    for service_count in service_counts:
        count = service_count
        if re.match(r"^.*:\d+$", service_count):
            (service, count) = service_count.split(":")
            result[service] = count
    return result


def _get_services_dict():
    """
    Parse the services and service-count config setting, and return how many
    of each service should actually be started.  If setting is "AUTO" we will
    try to guess the number for the user.  If the setting is not understood
    in some manner, assume it to be AUTO.
    """
    result = {}
    requested = _get_requested_service_count()
    for service in _get_requested_services():
        args = [service]
        args.extend(SERVICE_COUNT[service])
        args.append(requested[service])
        result[service] = _calc_daemon_count(*args)
    return result


def _enable_services():
    """
    Enabled services requested by user through services and service-count
    config settings.  Function will also disable services that are not
    requested by the user.
    """
    services = _get_services_dict()
    juju.juju_log("Selected Services: %s" % services.keys())

    # Take an extra step to implicitly disable any service that was not
    # specified in the "services" setting.
    for service in SERVICE_COUNT:
        if service not in services:
            services[service] = 0
    for service in services:
        juju.juju_log("Enabling: %s" % service)
        if service == "static" and services[service] > 0:
            _setup_apache()
        else:
            variable = SERVICE_DEFAULT[service]
            value = services[service]
            if value == 1:
                value = "yes"
            elif value == 0:
                value = "no"
            _replace_in_file(
                LANDSCAPE_DEFAULT_FILE,
                r"^%s=.*$" % variable,
                "%s=%s" % (variable, value))


def _format_service(name, count, port=None, httpchk="GET / HTTP/1.0",
        server_options="check inter 5000 rise 2 fall 5 maxconn 50",
        service_options=None, errorfiles=None):
    """
    Given a name and port, define a service in python data-structure
    format that will be exported as a yaml config to be set int a
    relation variable.  Override options by altering SERVICE_PROXY.

    @param name Name of the service (letters, numbers, underscores)
    @param count How many instances of this service will be started (int)
    @param port Port this service will be running on
    @param server_options override the server_options (String)
    @param httpchk The httpchk option, will be appeneded to service_options
    @param service_options override the service_options (Array of strings)
    @param errorfiles Provide a set of errorfiles for the service
    """
    if service_options is None:
        service_options = ["mode http", "balance leastconn"]
    if httpchk is not None:
        httpchk_option = "option httpchk %s" % httpchk
        service_options.append(httpchk_option)
    if errorfiles is None:
        errorfiles = []
    for errorfile in errorfiles:
        with open(errorfile["path"]) as handle:
            errorfile["content"] = b64encode(handle.read())

    host = juju.unit_get("private-address")
    result = {
        "service_name": name,
        "service_options": service_options,
        "servers": [[name, host, port, server_options]],
        "errorfiles": errorfiles}
    offset = 1
    while count - offset >= 1:
        result["servers"].append(
            [name, host, str(int(port) + offset), server_options])
        offset += 1
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
    service_count = _get_services_dict()
    for service in _get_requested_services():
        count = service_count[service]
        juju.juju_log("service: %s" % service)
        if service in SERVICE_PROXY:
            result.append(
                _format_service(service, count, **SERVICE_PROXY[service]))
    return result


def _lsctl(action):
    """ simple wrapper around lsctl, mostly to easily allow mocking"""
    check_call(["lsctl", action])


def _set_maintenance():
    """
    Put into maintenance mode, or take it out, depending on the read value of
    "maintenance" from the juju settings.  Non-boolean settings will be
    interpreted as False.
    """
    maintenance = juju.config_get("maintenance")
    if maintenance:
        juju.juju_log("Putting unit into maintenance mode")
        with open(LANDSCAPE_MAINTENANCE, "w") as fp:
            fp.write("%s" % datetime.datetime.now())
    else:
        if os.path.exists(LANDSCAPE_MAINTENANCE):
            juju.juju_log("Remove unit from maintenance mode")
            os.unlink(LANDSCAPE_MAINTENANCE)


def _set_upgrade_schema():
    """
    Alter the state of the UPGRADE_SCHEMA flag in the landscape default file.
    Consults the value of the "upgrade-schema" juju setting for the desired
    state.
    """
    upgrade_schema = juju.config_get("upgrade-schema")
    if upgrade_schema:
        value = "yes"
    else:
        value = "no"
    _replace_in_file(
        LANDSCAPE_DEFAULT_FILE,
        r"^#*%s=.*$" % "UPGRADE_SCHEMA",
        "%s=%s" % ("UPGRADE_SCHEMA", value))


def _is_db_up():
    """
    Return True if the database is accessible and read/write, False otherwise.
    """
    parser = RawConfigParser()
    parser.read([LANDSCAPE_SERVICE_CONF])
    try:
        database = parser.get("stores", "main")
        host = parser.get("stores", "host")
        user = parser.get("stores", "user")
        password = parser.get("stores", "password")
    except Error:
        return False
    else:
        return util.is_db_up(database, host, user, password)


ERROR_PATH = "/opt/canonical/landscape/canonical/landscape/static/offline/"
ERROR_FILES = [
    {"http_status": 403,
     "path": ERROR_PATH + "unauthorized-haproxy.html"},
    {"http_status": 500,
     "path": ERROR_PATH + "exception-haproxy.html"},
    {"http_status": 502,
     "path": ERROR_PATH + "unplanned-offline-haproxy.html"},
    {"http_status": 503,
     "path": ERROR_PATH + "unplanned-offline-haproxy.html"},
    {"http_status": 504,
     "path": ERROR_PATH + "timeout-haproxy.html"}]

SERVICE_PROXY = {
    "static": {"port": "80"},
    "appserver": {
        "port": "8080",
        "errorfiles": deepcopy(ERROR_FILES)},
    "msgserver": {
        "port": "8090", "httpchk": "HEAD /index.html HTTP/1.0",
        "errorfiles": deepcopy(ERROR_FILES)},
    "pingserver": {
        "port": "8070", "httpchk": "HEAD /ping HTTP/1.0",
        "errorfiles": deepcopy(ERROR_FILES)},
    "combo-loader": {
        "port": "9070",
        "httpchk": "HEAD /?yui/scrollview/scrollview-min.js HTTP/1.0",
        "errorfiles": deepcopy(ERROR_FILES)},
    "async-frontend": {"port": "9090"},
    "apiserver": {"port": "9080"},
    "package-upload": {"port": "9100"},
    "package-search": {"port": "9090"}}

# Format is:
#   [min, auto_max, hard_max]
#   min = minimum number of daemons to launch
#   auto_max = if auto-determining, only suggest this as the max
#   hard_max = hard-cutoff, cannot launch more than this.
SERVICE_COUNT = {
    "appserver": [1, 4, 9],
    "msgserver": [2, 8, 9],
    "pingserver": [1, 4, 9],
    "apiserver": [1, 2, 9],
    "combo-loader": [1, 1, 1],
    "async-frontend": [1, 1, 1],
    "jobhandler": [1, 1, 1],
    "package-upload": [1, 1, 1],
    "package-search": [1, 1, 1],
    "juju-sync": [1, 1, 1],
    "cron": [1, 1, 1],
    "static": [1, 1, 1]}


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
LANDSCAPE_NEW_SERVICE_CONF = "/etc/landscape/service.conf.new"
LANDSCAPE_SERVICE_CONF = "/etc/landscape/service.conf"
LANDSCAPE_MAINTENANCE = "/opt/canonical/landscape/maintenance.txt"
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
