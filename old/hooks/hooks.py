#!/usr/bin/env python
"""
hooks.py - entrypoint script for all landscape hooks
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from lib import util
from lib.juju import Juju

from base64 import b64encode, b64decode
from configobj import ConfigObj, ConfigObjError
from contextlib import closing
from copy import deepcopy
import cStringIO
import datetime
import grp
import os
import psutil
import pwd
import pycurl
import re
import shutil
import sys
import yaml
from subprocess import check_call, check_output, CalledProcessError, call


SSL_CERT_LOCATION = "/etc/ssl/certs/landscape_server_ca.crt"


def _get_installed_version(name):
    """Returns the version string of name using dpkg-query or returns None"""
    try:
        version = check_output(
            ["dpkg-query", "--show", "--showformat=${Version}", name])
    except CalledProcessError:
        juju.juju_log(
            "Cannot determine version of %s. Package is not installed." %
            name)
        return None
    return version


def _create_maintenance_user(password, host, admin, admin_password):
    """
    Any LDS version prior to 14.01 needs a C{landscape_maintenance} database
    user.  Create this user if needed with the provided password on the host
    using the admin/admin_password credentials. Otherwise, do nothing.
    """
    version = _get_installed_version("landscape-server")
    if version is None:
        return

    if call(["dpkg", "--compare-versions", version, "ge", "14.01"]) == 0:
        # We are on 14.01 or greater. No landscape_maintenance needed
        return

    juju.juju_log("Creating landscape_maintenance user")
    util.create_user(
        "landscape_maintenance", password, host, admin, admin_password)


def _get_config_obj(config_source=None):
    """Create a ConfigObj based on reading the config file C{filename}.
    Shamelessly leveraged from landscape-client: deployment.py
    """
    if config_source is None:
        config_source = LANDSCAPE_SERVICE_CONF
    try:
        config_obj = ConfigObj(config_source, list_values=False,
                               raise_errors=False, write_empty_values=True)
    except ConfigObjError, e:
        juju.juju_log(str(e), "WARNING")
        # Good configuration values are recovered here
        config_obj = e.config
    return config_obj


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
    for id in juju.relation_ids("website"):
        juju.relation_set(
            relation_id=id,
            services=yaml.safe_dump(_get_services_haproxy()))


def _get_haproxy_service_name():
    """
    Find out what service name was used to deploy haproxy and sanitize it
    according to the jinja requirements. The service name is used as a
    variable name in the apache vhost jinja template.

    For example, if haproxy is deployed as "landscape-haproxy", the apache
    charm will transform that into landscapehaproxy.
    """
    haproxy_relations = juju.relation_ids("website")
    if not haproxy_relations:
        return None
    haproxy_relation_units = juju.relation_list(haproxy_relations[0])
    if not haproxy_relation_units:
        return None
    haproxy_service = haproxy_relation_units[0].rsplit("/", 1)[0]
    # jinja2 templates require python-type variables, remove all characters
    # that do not comply
    haproxy_service = re.sub("\W", "", haproxy_service)
    return haproxy_service


def _get_vhost_template(template_filename, haproxy_service_name):
    """Expand the template with the provided haproxy service name."""
    with open("%s/config/%s" % (ROOT, template_filename), "r") as handle:
        contents = handle.read()
        contents = re.sub(r"{{ haproxy_([^}]+) }}", r"{{ %s_\1 }}" %
                          haproxy_service_name, contents)
    return contents


def notify_vhost_config_relation(haproxy_service_name, relation_id=None):
    """
    Notify the vhost-config relation.

    This will mark it "ready to proceed".  If relation_id is specified
    use that as the relation context, otherwise look up and notify all
    vhost-config relations.

    The haproxy_service_name is needed so that the vhost template can be
    adjusted with the correct jinja variable that apache will look for.
    """
    vhosts = []
    vhostssl_template = "vhostssl.tmpl"
    vhost_template = "vhost.tmpl"
    if HAS_OLD_ERROR_PATH:
        # This means we're installing a 14.10 or 13.09 release, with old
        # apache setup.
        vhostssl_template += ".legacy"
        vhost_template += ".legacy"
    contents = _get_vhost_template(vhostssl_template, haproxy_service_name)
    vhosts.append({"port": "443", "template": b64encode(contents)})
    contents = _get_vhost_template(vhost_template, haproxy_service_name)
    vhosts.append({"port": "80", "template": b64encode(contents)})
    relation_ids = [relation_id]
    if relation_id is None:
        relation_ids = juju.relation_ids("vhost-config")
    for relation_id in relation_ids:
        juju.relation_set(relation_id=relation_id, vhosts=yaml.dump(vhosts))


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
        juju.juju_log(
            "Need host, user and password in relation before proceeding")
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
            "Our database is clustered with %s units. "
            "Ignoring any intermittent 'standalone' states."
            % relation_count)
        ignored_states.add("standalone")

    if remote_state is None or remote_state in ignored_states:
        juju.juju_log(
            "No config changes made. Invalid state '%s' for host %s." %
            (remote_state, host))
        return

    juju.juju_log("Updating config due to database changes.")

    if not util.is_db_up("postgres", host, admin, admin_password):
        juju.juju_log(
            "Ignoring config changes. Because new service settings don't "
            "have proper permissions setup on the host %s." % host)
        return

    # Changes are validated; db is up has write-accessible
    update_config_settings(
        {"stores": {"host": host, "port": "5432", "user": user,
                    "password": password},
         "schema": {"store_user": admin, "store_password": admin_password}})

    with closing(util.connect_exclusive(host, admin, admin_password)):
        util.create_user(user, password, host, admin, admin_password)
        _create_maintenance_user(password, host, admin, admin_password)
        check_call("setup-landscape-server")
        juju.juju_log("Landscape database initialized!")

    # Fire dependent changed hooks
    vhost_config_relation_changed()

    try:
        # Handle remove-relation db-admin.  This call will fail because
        # database access has already been removed.
        config_changed()  # only restart if is_db_up and _is_amqp_up
    except Exception as e:
        juju.juju_log(str(e), level="DEBUG")


def _get_db_access_details():
    """
    Returns the main database access details as they are set in the landscape
    service configuration file.
    """
    config_obj = _get_config_obj(LANDSCAPE_SERVICE_CONF)
    try:
        section = config_obj["stores"]
        database = section["main"]
        db_host = section["host"]
        db_user = section["user"]
        db_password = section["password"]
    except KeyError:
        return None
    return (database, db_host, db_user, db_password)


def _create_first_admin():
    """
    If so requested by the presence of the right configuration keys,
    tries to create the landscape first administrator and, as a consequence,
    the standalone account too.
    """
    first_admin_email = juju.config_get("admin-email")
    first_admin_name = juju.config_get("admin-name")
    first_admin_password = juju.config_get("admin-password")
    if not all((first_admin_email, first_admin_name, first_admin_password)):
        juju.juju_log("Not creating a Landscape administrator: need "
                      "admin-email, admin-name and admin-password.")
        return False
    juju.juju_log("First admin creation requested")
    access_details = _get_db_access_details()
    if not access_details:
        juju.juju_log("No DB configuration yet, bailing.")
        return False
    database, db_host, db_user, db_password = access_details
    if util.is_db_up(database, db_host, db_user, db_password):
        with closing(util.connect_exclusive(db_host, db_user, db_password)):
            return util.create_landscape_admin(
                db_user, db_password, db_host, first_admin_name,
                first_admin_email, first_admin_password)
    else:
        juju.juju_log("Can't talk to the DB yet, bailing.")
        return False


def amqp_relation_joined():
    juju.relation_set("username=landscape")
    juju.relation_set("vhost=landscape")


def _chown(dir_path, owner="landscape"):
    """Ensure the provided C{path} is owned by C{owner}"""
    uid = pwd.getpwnam(owner).pw_uid
    gid = grp.getgrnam(owner).gr_gid
    os.chown(dir_path, uid, gid)
    os.chmod(dir_path, 0o777)
    for dirpath, dirnames, filenames in os.walk(dir_path):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            os.chown(path, uid, gid)


def data_relation_changed():
    juju.juju_log(
        "External storage relation changed: "
        "requesting mountpoint %s from storage charm" % STORAGE_MOUNTPOINT)
    juju.relation_set("mountpoint=%s" % STORAGE_MOUNTPOINT)

    # Has storage charm setup the mountpoint we requested?
    #
    # Since relation-data is one-way communication, the mountpoint we "set"
    # above is only visible from a relation_get on the storage subordinate side
    # of the relation. Hence, our relation_get here will only return non-None
    # if the storage subordinate has called relation_set("mountpoint=X") on its
    # side to announce that it has succeeded in attaching the requested
    # mountpoint we sent above.
    mountpoint = juju.relation_get("mountpoint")
    if mountpoint != STORAGE_MOUNTPOINT:
        juju.juju_log(
            "Awaiting storage mountpoint intialisation from storage relation")
        sys.exit(0)

    if not os.path.exists(mountpoint):
        juju.juju_log(
            "Error: Mountpoint %s doesn't appear to exist" % mountpoint)
        sys.exit(1)

    # Migrate existing logs
    juju.juju_log(
        "External volume mounted at %s. Migrating data and updating config"
        % mountpoint)

    unit_name = juju.local_unit()
    new_path = "%s/%s" % (mountpoint, unit_name)

    config_obj = _get_config_obj()
    try:
        log_path = config_obj["global"]["log-path"]
        repo_path = config_obj["landscape"]["repository-path"]
    except KeyError:
        juju.juju_log(
            "Error: can't read landscape config %s" % LANDSCAPE_SERVICE_CONF)
        sys.exit(1)
    else:
        new_log_path = "%s/logs" % new_path
        # Shared repository path is shared by all units
        new_repo_path = "%s/landscape-repository" % mountpoint

        if new_log_path != log_path:
            _lsctl("stop")  # Stop services before migrating logfiles
            juju.juju_log("Migrating log data to %s" % new_log_path)
            if not os.path.exists(new_log_path):
                os.makedirs(new_log_path)
            check_call(
                "cp -f %s/*log %s" % (log_path, new_log_path), shell=True)
            _chown(new_log_path)  # to set landscape owner of all files
        if new_repo_path != repo_path:
            # Migrate repository data if any exist
            if not os.path.exists(new_repo_path):
                os.makedirs(new_repo_path)
                _chown(new_repo_path, owner="root")  # root since shared
            if os.path.exists(repo_path) and len(os.listdir(repo_path)):
                _lsctl("stop")  # Stop services before migrating repo data
                juju.juju_log(
                    "Migrating repository data to %s" % new_repo_path)
                check_call(
                    "cp -r %s/* %s" % (repo_path, new_repo_path), shell=True)
            else:
                juju.juju_log("No repository data migrated")

    # Change logs and repository path to our new nfs mountpoint
    update_config_settings(
        {"global": {"oops-path": "%s/logs" % new_path,
                    "log-path": new_log_path},
         "landscape": {"repository-path": new_repo_path}})
    config_changed()  # only starts services again if is_db_up and _is_amqp_up


def update_config_settings(config_settings, outfile=None):
    config_obj = _get_config_obj(LANDSCAPE_SERVICE_CONF)
    changes = False
    for section_name, section in config_settings.iteritems():
        if not section_name in config_obj:
            config_obj[section_name] = {}
        for key, value in section.iteritems():
            if config_obj[section_name].get(key, None) != value:
                changes = True
                config_obj[section_name][key] = value
    if changes:
        if outfile is None:
            config_obj.filename = LANDSCAPE_SERVICE_CONF
        else:
            config_obj.filename = outfile
        config_obj.write()


def _is_amqp_up():
    """Return C{True} if the ampq-relation has defined required values"""
    relid = juju.relation_ids("amqp")[0]         # TODO support amqp clusters?
    amqp_unit = juju.relation_list(relid)[0]     # TODO support amqp clusters?

    host = juju.relation_get(
        "hostname", unit_name=amqp_unit, relation_id=relid)
    password = juju.relation_get(
        "password", unit_name=amqp_unit, relation_id=relid)
    if not host or not password:
        juju.juju_log(
            "Waiting for valid hostname/password values from amqp relation")
        return False
    return True


def amqp_relation_changed():
    if not _is_amqp_up():
        sys.exit(0)

    password = juju.relation_get("password")
    host = juju.relation_get("hostname")

    juju.juju_log("Using AMQP server at %s" % host)

    update_config_settings(
        {"broker": {"password": password, "host": host, "user": "landscape"}})

    if _is_db_up():
        config_changed()


def vhost_config_relation_changed():
    """Relate to apache to configure a vhost.

    This hook will supply vhost configuration as well as read simple data
    out of apache (servername, certificate).  This data is necessary for
    informing clients of the correct URL and cert to use when connecting
    to the server.
    """
    # If this unit is not participating in a vhost-config relation, noop
    if not juju.relation_ids("vhost-config"):
        return

    # If we are not related to haproxy yet, noop, because we need to know the
    # haproxy service name so we can set the template variable to the correct
    # name in the apache vhost template.
    haproxy_service_name = _get_haproxy_service_name()
    if not haproxy_service_name:
        return

    notify_vhost_config_relation(haproxy_service_name,
                                 os.environ.get("JUJU_RELATION_ID", None))

    access_details = _get_db_access_details()
    if not access_details:
        juju.juju_log("Database not ready yet, deferring call")
        sys.exit(0)
    database, host, user, password = access_details

    relids = juju.relation_ids("vhost-config")
    if relids:
        relid = relids[0]
        apache2_unit = juju.relation_list(relid)[0]
        apache_servername = juju.relation_get(
            "servername", unit_name=apache2_unit, relation_id=relid)
    else:
        apache_servername = juju.relation_get("servername")

    if not apache_servername:
        juju.juju_log("Waiting for data from apache, deferring")
        sys.exit(0)
    apache_url = "https://%s/" % apache_servername

    if not _is_db_up():
        juju.juju_log("Waiting for database to become available, deferring.")
        sys.exit(0)

    with closing(util.connect_exclusive(host, user, password)):
        juju.juju_log("Updating Landscape root_url: %s" % apache_url)
        util.change_root_url(database, user, password, host, apache_url)

    # This data may or may not be present, dependeing on if cert is self
    # signed from apache.
    ssl_cert = juju.relation_get(
        "ssl_cert", unit_name=apache2_unit, relation_id=relid)
    if ssl_cert:
        juju.juju_log("Writing new SSL cert: %s" % SSL_CERT_LOCATION)
        with open(SSL_CERT_LOCATION, 'w') as f:
            f.write(str(b64decode(ssl_cert)))
    else:
        if os.path.exists(SSL_CERT_LOCATION):
            os.remove(SSL_CERT_LOCATION)

    # only starts services again if is_db_up and _is_amqp_up
    config_changed()


def config_changed():
    """Update and restart services based on config setting changes.

    This hook is called either by the config-changed hook or other hooks when
    something has modified configuration values. Before any changes, we stop
    all landscape services and call _set_maintenance to ensure we are in proper
    maintenance state before attempting to enable any periodic processes or
    services.
    """
    _lsctl("stop")
    _install_license()
    _set_maintenance()
    _enable_services()
    _set_upgrade_schema()
    _create_first_admin()

    if _is_db_up() and _is_amqp_up():
        _lsctl("start")

    notify_website_relation()


def _download_file(url, Curl=pycurl.Curl):
    """ Download from a url and save to the filename given """
    # Fix for CVE-2014-8150, urls cannot end with newline
    url = url.rstrip()
    buf = cStringIO.StringIO()
    juju.juju_log("Fetching License: %s" % url)
    curl = Curl()
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
    Setup apache2 to serve static landscape content, removing everything else.

    N.B. As of Trusty, sites must be named with '.conf' at the end.
    Precise and Trusty can then both use a2ensite/a2dissite with 'file.conf'.
    """
    public = juju.unit_get("public-address")
    _a2enmods(["rewrite", "proxy_http", "ssl", "headers", "expires"])
    sites_available = os.listdir(os.path.dirname(LANDSCAPE_APACHE_SITE))
    for site in sites_available:
        _a2dissite(site)
    conf_path = "%s/hooks/conf/landscape-http" % ROOT
    if HAS_OLD_ERROR_PATH:
        conf_path += ".legacy"
    shutil.copy(conf_path, LANDSCAPE_APACHE_SITE)
    _replace_in_file(LANDSCAPE_APACHE_SITE, r"@hostname@", public)
    _a2ensite("landscape.conf")
    _service("apache2", "restart")


def _install_license():
    """
    If a license was given, either in plain text or in the form of a URL,
    write its contents to the file specified by LANDSCAPE_LICENSE_DEST.
    """
    license_file_re = r"^(file://|http://|https://).*$"
    license_file = juju.config_get("license-file")
    if not license_file:
        juju.juju_log("No license file given, skipping")
        return
    else:
        # Leading or trailing whitespace is nonsensical, so remove it.
        license_file = license_file.strip()

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
        # Only remove maintenance mode when we are sure the db is up
        # otherwise cron scripts like maas-poller will traceback per lp:1272140
        # Also validate is_amqp_up as well otherwise we receive
        # twisted.internet.error.ConnectionRefusedError:
        if os.path.exists(LANDSCAPE_MAINTENANCE):
            if _is_db_up() and _is_amqp_up():
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
    access_details = _get_db_access_details()
    if not access_details:
        return False
    database, host, user, password = access_details
    return util.is_db_up(database, host, user, password)


ERROR_PATH_OLD = "/opt/canonical/landscape/canonical/landscape/static/offline/"
ERROR_PATH_NEW = "/opt/canonical/landscape/canonical/landscape/offline/"
HAS_OLD_ERROR_PATH = os.path.exists(ERROR_PATH_OLD)
ERROR_PATH = ERROR_PATH_OLD if HAS_OLD_ERROR_PATH else ERROR_PATH_NEW
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
        "port": "8090", "httpchk": "HEAD /index.html HTTP/1.0"
        },
    "pingserver": {
        "port": "8070", "httpchk": "HEAD /ping HTTP/1.0"
        },
    "combo-loader": {
        "port": "9070",
        "httpchk": "HEAD /?yui/scrollview/scrollview-min.js HTTP/1.0"
        },
    "async-frontend": {
        "port": "9090",
        "service_options": ["timeout client 300000",
                            "timeout server 300000"]},
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
LANDSCAPE_APACHE_SITE = "/etc/apache2/sites-available/landscape.conf"
LANDSCAPE_LICENSE_DEST = "/etc/landscape/license.txt"
LANDSCAPE_SERVICE_CONF = "/etc/landscape/service.conf"
LANDSCAPE_MAINTENANCE = "/opt/canonical/landscape/maintenance.txt"
STORAGE_MOUNTPOINT = "/srv/juju/vol-0001"
ROOT = os.path.abspath(os.path.curdir)
juju = Juju()

if __name__ == "__main__":
    hooks = {
        "config-changed": config_changed,
        "amqp-relation-joined": amqp_relation_joined,
        "amqp-relation-changed": amqp_relation_changed,
        "data-relation-changed": data_relation_changed,
        "db-admin-relation-joined": db_admin_relation_joined,
        "db-admin-relation-changed": db_admin_relation_changed,
        "website-relation-joined": website_relation_joined,
        "vhost-config-relation-changed": vhost_config_relation_changed}
    hook = os.path.basename(sys.argv[0])
    # If the hook is unsupported, let it raise a KeyError and exit with error.
    hooks[hook]()
