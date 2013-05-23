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
from subprocess import (check_call, check_output)
from ConfigParser import RawConfigParser

juju = Juju()

SERVICE = {"static": {"port": "80"},
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

def _get_services():
    """
    Get the services that were configured to run.  Return in a format
    understood by haproxy.
    """
    config = juju.config_get()
    services = []
    if "services" in config:
        for service in config["services"].split():
            if service not in SERVICE:
                juju.juju_log("Invalid Service: %s" % service)
                continue
            juju.juju_log("service: %s" % service)
            services.append(_format_service(service, **SERVICE[service]))
    return services

def website_relation_joined():
    host = juju.unit_get("private-address")
    # N.B.: Port setting necessary do to limitations with haproxy charm
    juju.relation_set(
            services=yaml.safe_dump(_get_services()), hostname=host, port=80)

def db_admin_relation_joined():
    db_admin_relation_changed()

def db_admin_relation_changed():
    util.set_host("account-1")
    util.set_host("knowledge")
    util.set_host("main")
    util.set_host("package")
    util.set_host("resource-1")
    util.set_host("session")

    host = check_output(["relation-get", "host"]).strip()
    admin = check_output(["relation-get", "user"]).strip()
    admin_password = check_output(["relation-get", "password"]).strip()
    user = "landscape"
    password = "landscape"

    if host:
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


###############################################################################
# Main section
###############################################################################
if __name__ == "__main__":
    hook = os.path.basename(sys.argv[0]).replace("-", "_")
    eval("%s()" % hook)
