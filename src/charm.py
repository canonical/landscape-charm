#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

import logging
import os
from base64 import b64decode, b64encode, binascii
from configparser import ConfigParser
from subprocess import CalledProcessError, check_call

import yaml

from charms.operator_libs_linux.v0.apt import (
    PackageError, PackageNotFoundError, add_package)

from ops.charm import (
    CharmBase, InstallEvent, RelationChangedEvent, RelationJoinedEvent,
    UpdateStatusEvent)
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus)

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS = "/etc/default/landscape-server"
SERVICE_CONF = "/etc/landscape/service.conf"
SSL_CERT_PATH = "/etc/ssl/certs/landscape_server_ca.crt"
HAPROXY_CONFIG_FILE = os.path.join(os.path.dirname(__file__),
                                   "haproxy-config.yaml")
LSCTL = "/usr/bin/lsctl"


class LandscapeServerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._update_status)
        self.framework.observe(self.on.update_status, self._update_status)
        self.framework.observe(self.on.db_relation_joined,
                               self._db_relation_changed)
        self.framework.observe(self.on.db_relation_changed,
                               self._db_relation_changed)
        self.framework.observe(self.on.amqp_relation_joined,
                               self._amqp_relation_joined)
        self.framework.observe(self.on.amqp_relation_changed,
                               self._amqp_relation_changed)
        self.framework.observe(self.on.website_relation_joined,
                               self._website_relation_joined)
        self.framework.observe(self.on.website_relation_changed,
                               self._website_relation_changed)

        self._stored.set_default(ready={
            "db": False,
            "amqp": False,
            "haproxy": False,
        })
        self._stored.set_default(running=False)

    def _on_config_changed(self, _) -> None:
        pass

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing apt packages")

        landscape_ppa = self.model.config["landscape_ppa"]

        try:
            # Add the Landscape Server beta PPA and install via apt.
            check_call(["add-apt-repository", "-y", landscape_ppa])
            add_package("landscape-server")
        except PackageNotFoundError:
            logger.error("landscape-server package not found in package cache "
                         "or on system")
            self.unit.status = BlockedStatus("Failed to install packages")
        except PackageError as e:
            logger.error(
                "Could not install landscape-server package. Reason: %s",
                e.message)
            self.unit.status = BlockedStatus("Failed to install packages")
        except CalledProcessError as e:
            logger.error("Package install failed with return code %d",
                         e.returncode)
            self.unit.status = BlockedStatus("Failed to install packages")

        # Write the config-provided SSL certificate, if it exists.
        config_ssl_cert = self.model.config["ssl_cert"]

        if config_ssl_cert != "DEFAULT":
            self.unit.status = MaintenanceStatus("Installing SSL certificate")
            self._write_ssl_cert(config_ssl_cert)

    def _update_status(self, event: UpdateStatusEvent) -> None:
        """Called at regular intervals by juju."""
        self._update_ready_status()

    def _update_ready_status(self) -> None:
        """If all relations are prepared, updates unit status to Active."""
        if isinstance(self.unit.status, BlockedStatus):
            return

        if not all(self._stored.ready.values()):
            waiting_on = [
                rel for rel, ready in self._stored.ready.items() if not ready]
            self.unit.status = WaitingStatus(
                "Waiting on relations: {}".format(", ".join(waiting_on)))
            return

        if self._stored.running:
            self.unit.status = ActiveStatus("Unit is ready")
            return

        self._stored.running = self._start_services()

    def _start_services(self) -> bool:
        """
        Starts all Landscape Server systemd services. Returns True if
        successful, False otherwise.
        """
        self.unit.status = MaintenanceStatus("Starting services")

        self._update_default_settings("RUN_ALL", "yes")

        try:
            check_call([LSCTL, "restart"])
            self.unit.status = ActiveStatus("Unit is ready")
            return True
        except CalledProcessError as e:
            logger.error("Starting services failed with output: %s", e.output)
            self.unit.status = BlockedStatus("Failed to start services")
            return False

    def _db_relation_changed(self, event: RelationChangedEvent) -> None:
        unit_data = event.relation.data[event.unit]

        # Using "master" key as a quick indicator of readiness.
        if "master" not in unit_data:
            logger.info("db relation not yet ready")
            self._update_ready_status()
            return

        allowed_units = unit_data["allowed-units"].split()
        if self.unit.name not in allowed_units:
            logger.info("%s not in allowed_units")
            self._update_ready_status()
            return

        self._stored.ready["db"] = False
        self.unit.status = MaintenanceStatus("Setting up databases")

        host = unit_data["host"]
        port = unit_data["port"]
        user = unit_data["user"]
        password = unit_data["password"]

        self._update_service_conf({
            "stores": {
                "host": "{}:{}".format(host, port),
                "password": password,
            },
            "schema": {
                "store_user": user,
                "store_password": password,
            },
        })

        # Ensure the database users and schemas are set up.
        try:
            check_call(["/usr/bin/landscape-schema", "--bootstrap"])
        except CalledProcessError as e:
            logger.error(
                "Landscape Server schema update failed with return code %d",
                e.returncode)
            self.unit.status = BlockedStatus(
                "Failed to update database schema")
            return

        self._stored.ready["db"] = True
        self._update_ready_status()

    def _amqp_relation_joined(self, event: RelationJoinedEvent) -> None:
        self._stored.ready["amqp"] = False
        self.unit.status = MaintenanceStatus("Setting up amqp connection")

        event.relation.data[self.unit].update({
            "username": "landscape",
            "vhost": "landscape",
        })

    def _amqp_relation_changed(self, event):
        unit_data = event.relation.data[event.unit]

        if "password" not in unit_data:
            logger.info("rabbimq-server has not sent password yet")
            return

        hostname = unit_data["hostname"]
        password = unit_data["password"]

        self._update_service_conf({
            "broker": {
                "host": ",".join(hostname),
                "password": password,
            }
        })

        self._stored.ready["amqp"] = True
        self._update_ready_status()

    def _website_relation_joined(self, event: RelationJoinedEvent) -> None:
        self._stored.ready["haproxy"] = False
        self.unit.status = MaintenanceStatus("Setting up haproxy connection")

        # Check the SSL cert stuff first. No sense doing all the other
        # work just to fail here.
        ssl_cert = self.model.config["ssl_cert"]
        ssl_key = self.model.config["ssl_key"]

        if ssl_cert != "DEFAULT" and ssl_key == "":
            # We have a cert but no key, this is an error.
            self.unit.status = BlockedStatus(
                "`ssl_cert` is specified but `ssl_key` is missing")
            return

        if ssl_cert != "DEFAULT":
            try:
                ssl_cert = b64decode(ssl_cert)
                ssl_key = b64decode(ssl_key)
                ssl_cert = b64encode(ssl_cert + b"\n" + ssl_key)
            except binascii.Error:
                self.unit.status = BlockedStatus(
                    "Unable to decode `ssl_cert` or `ssl_key` - must be "
                    "b64-encoded")
                return

        with open(HAPROXY_CONFIG_FILE) as haproxy_config_file:
            haproxy_config = yaml.safe_load(haproxy_config_file)

        http_service = haproxy_config["http_service"]
        https_service = haproxy_config["https_service"]
        https_service["crts"] = [ssl_cert]

        server_ip = event.relation.data[self.unit]["private-address"]
        unit_name = self.unit.name.replace("/", "-")
        worker_counts = self.model.config["worker_counts"]

        appservers, pingservers, message_servers, api_servers = [
            [(
                "landscape-{}-{}-{}".format(name, unit_name, i),
                server_ip,
                haproxy_config["ports"][name] + i,
                haproxy_config["server_options"],
            ) for i in range(worker_counts)]
            for name in ("appserver", "pingserver", "message-server", "api")
        ]

        http_service["servers"] = appservers
        http_service["backends"] = [{
            "backend_name": "landscape-ping",
            "servers": pingservers,
        }]
        https_service["servers"] = appservers
        https_service["backends"] = [{
            "backend_name": "landscape-message",
            "servers": message_servers,
        }, {
            "backend_name": "landscape-api",
            "servers": api_servers,
        }]

        # TODO: sort out pppa-proxy servers/backends

        error_files_location = haproxy_config["error_files"]["location"]
        error_files = []
        for code, filename in haproxy_config["error_files"]["files"].items():
            error_file_path = os.path.join(error_files_location, filename)
            with open(error_file_path, "rb") as error_file:
                error_files.append({
                    "http_status": code,
                    "content": b64encode(error_file.read())
                })

        http_service["error_files"] = error_files
        https_service["error_files"] = error_files

        event.relation.data[self.unit].update({
            "services": yaml.safe_dump([http_service, https_service])
        })

        self._stored.ready["haproxy"] = True
        self._update_ready_status()

    def _website_relation_changed(self, event: RelationChangedEvent) -> None:
        """
        Writes the HAProxy-provided SSL certificate for
        Landscape Server, if config has not provided one.
        """
        config_ssl_cert = self.model.config["ssl_cert"]

        if config_ssl_cert != "DEFAULT":
            # No-op: cert has been provided by config.
            return

        if "ssl_cert" not in event.relation.data[event.unit]:
            return

        self.unit.status = MaintenanceStatus(
            "Installing HAProxy SSL certificate")
        haproxy_ssl_cert = event.relation.data[event.unit]["ssl_cert"]

        self._write_ssl_cert(haproxy_ssl_cert)
        self._update_ready_status()

    def _update_service_conf(self, updates: dict) -> None:
        """
        Updates the Landscape Server configuration file.

        `updates`: a mapping of {section => {key => value}}, to be
            applied to the config file.
        """
        config = ConfigParser()
        config.read(SERVICE_CONF)

        for section, data in updates.items():
            for key, value in data.items():
                config[section][key] = value

        with open(SERVICE_CONF, "w") as config_file:
            config.write(config_file)

    def _update_default_settings(self, key: str, value: str) -> None:
        """Updates the Landscape Server default settings file."""
        with open(DEFAULT_SETTINGS, "r") as settings_file:
            new_lines = []
            for i, line in enumerate(settings_file):
                if line.startswith(key + "="):
                    new_line = "{}=\"{}\"\n".format(key, value)
                else:
                    new_line = line

                new_lines.append(new_line)

        with open(DEFAULT_SETTINGS, "w") as settings_file:
            settings_file.write("".join(new_lines))

    def _write_ssl_cert(self, ssl_cert: str) -> None:
        """Decodes and writes `ssl_cert` to SSL_CERT_PATH."""
        with open(SSL_CERT_PATH, "wb") as ssl_cert_file:
            ssl_cert_file.write(b64decode(ssl_cert))


if __name__ == "__main__":  # pragma: no cover
    main(LandscapeServerCharm)
