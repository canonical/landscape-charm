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

def _format_service(name, port,
        server_options="check inter 2000 rise 2 fall 5 maxconn 50",
        service_options=["mode http", "balance leastconn",
            "option httpchk GET / HTTP/1.0"]):
    """
    Given a name and port, define a service in python data-structure
    format that will be exported as a yaml config to be set int a
    relation variable.

    @param name Name of the service (letters, numbers, underscores)
    @param port Port this service will be running on
    @param server_options override the server_options (String)
    @param service_options override the service_options (Array of strings)
    """
    host = juju.unit_get("private-address")
    server_options = "check inter 2000 rise 2 fall 5 maxconn 50"
    result = {
        "service_name": name, 
        "service_options": service_options,
        "servers": [[name, host, port, server_options]]}
    return result

def _get_services():
    config = juju.config_get()
    services = []
    if "services" in config:
        for service in config["services"].split():
            juju.juju_log("service: %s" % service)
            # TODO: need the port
            services.append(_format_service(service, "80"))
    services.append(_format_service("async", "10005"))
    services.append(_format_service("api", "10006"))
    services.append(_format_service("upload", "10008"))
    return services

def service_relation_joined():
    host = juju.unit_get("private-address")
    services = _get_services()
    # N.B.: Port setting necessary do to limitations with haproxy charm
    juju.relation_set(services=yaml.dump(services), hostname=host, port=80)

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

        # TODO: Move this out of here...
        check_call("setup-landscape-server")

        check_call(["lsctl", "restart"])

def db_proxy_relation_changed():
    db_relation_changed()

def db_relation_changed():
    host = check_output(["relation-get", "host"]).strip()
    user = "landscape"
    password = "landscape"
    hook_dir = os.path.dirname(__file__)
    sys.path.insert(0, hook_dir)

    if host:
        config_file = "/etc/landscape/service.conf"

        parser = RawConfigParser()
        parser.read([config_file])

        parser.set("stores", "host", host)
        parser.set("stores", "port", "5432")
        parser.set("stores", "user", user)
        parser.set("stores", "password", password)
        parser.set("schema", "store_user", user)
        parser.set("schema", "store_password", password)
        parser.set("schema", "host", host)

        with open(config_file, "w+") as output_file:
            parser.write(output_file)

        check_output([os.path.join(hook_dir, "start-services")])

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
