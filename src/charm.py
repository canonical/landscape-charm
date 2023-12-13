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
import subprocess
from base64 import b64decode, b64encode, binascii
from subprocess import CalledProcessError, check_call

import yaml

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError
from charms.operator_libs_linux.v0.passwd import group_exists, user_exists
from charms.operator_libs_linux.v0.systemd import service_reload

from ops.charm import (
    ActionEvent,
    CharmBase,
    InstallEvent,
    LeaderElectedEvent,
    LeaderSettingsChangedEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationJoinedEvent,
    UpdateStatusEvent,
)
from ops.framework import StoredState
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    Relation,
    MaintenanceStatus,
    WaitingStatus,
)

from settings_files import (
    DEFAULT_POSTGRES_PORT,
    configure_for_deployment_mode,
    merge_service_conf,
    prepend_default_settings,
    update_db_conf,
    update_default_settings,
    update_service_conf,
    write_license_file,
    write_ssl_cert,
)

logger = logging.getLogger(__name__)

DEBCONF_SET_SELECTIONS = "/usr/bin/debconf-set-selections"
DPKG_RECONFIGURE = "/usr/sbin/dpkg-reconfigure"
HAPROXY_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "haproxy-config.yaml")
LSCTL = "/usr/bin/lsctl"
NRPE_D_DIR = "/etc/nagios/nrpe.d"
POSTFIX_CF = "/etc/postfix/main.cf"
SCHEMA_SCRIPT = "/usr/bin/landscape-schema"
BOOTSTRAP_ACCOUNT_SCRIPT = "/opt/canonical/landscape/bootstrap-account"
HASH_ID_DATABASES = "/opt/canonical/landscape/hash-id-databases-ignore-maintenance"

LANDSCAPE_PACKAGES = (
    "landscape-server",
    "landscape-client",
    "landscape-common",
)

DEFAULT_SERVICES = (
    "landscape-api",
    "landscape-appserver",
    "landscape-async-frontend",
    "landscape-job-handler",
    "landscape-msgserver",
    "landscape-pingserver",
)
LEADER_SERVICES = (
    "landscape-package-search",
    "landscape-package-upload",
)

OPENID_CONFIG_VALS = (
    "openid_provider_url",
    "openid_logout_url",
)
OIDC_CONFIG_VALS = (
    "oidc_issuer",
    "oidc_client_id",
    "oidc_client_secret",
    "oidc_logout_url",
)


class LandscapeServerCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)

        # Lifecycle
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._update_status)
        self.framework.observe(self.on.update_status, self._update_status)

        # Relations
        self.framework.observe(self.on.db_relation_joined, self._db_relation_changed)
        self.framework.observe(self.on.db_relation_changed, self._db_relation_changed)
        self.framework.observe(self.on.amqp_relation_joined, self._amqp_relation_joined)
        self.framework.observe(
            self.on.amqp_relation_changed, self._amqp_relation_changed
        )
        self.framework.observe(
            self.on.website_relation_joined, self._website_relation_joined
        )
        self.framework.observe(
            self.on.website_relation_changed, self._website_relation_changed
        )
        self.framework.observe(
            self.on.website_relation_departed, self._website_relation_departed
        )
        self.framework.observe(
            self.on.nrpe_external_master_relation_joined,
            self._nrpe_external_master_relation_joined,
        )
        self.framework.observe(
            self.on.application_dashboard_relation_joined,
            self._application_dashboard_relation_joined,
        )

        # Leadership/peering
        self.framework.observe(self.on.leader_elected, self._leader_elected)
        self.framework.observe(
            self.on.leader_settings_changed, self._leader_settings_changed
        )
        self.framework.observe(
            self.on.replicas_relation_joined, self._on_replicas_relation_joined
        )
        self.framework.observe(
            self.on.replicas_relation_changed, self._on_replicas_relation_changed
        )

        # Actions
        self.framework.observe(self.on.pause_action, self._pause)
        self.framework.observe(self.on.resume_action, self._resume)
        self.framework.observe(self.on.upgrade_action, self._upgrade)
        self.framework.observe(self.on.migrate_schema_action, self._migrate_schema)
        self.framework.observe(
            self.on.hash_id_databases_action, self._hash_id_databases
        )

        # State
        self._stored.set_default(
            ready={
                "db": False,
                "amqp": False,
                "haproxy": False,
            }
        )
        self._stored.set_default(leader_ip="")
        self._stored.set_default(running=False)
        self._stored.set_default(paused=False)
        self._stored.set_default(default_root_url="")
        self._stored.set_default(account_bootstrapped=False)

        self.landscape_uid = user_exists("landscape").pw_uid
        self.root_gid = group_exists("root").gr_gid

    def _on_config_changed(self, _) -> None:
        prev_status = self.unit.status

        # Update additional configuration
        deployment_mode = self.model.config.get("deployment_mode")
        update_service_conf({"global": {"deployment-mode": deployment_mode}})

        configure_for_deployment_mode(deployment_mode)

        additional_config = self.model.config.get("additional_service_config")
        if additional_config:
            merge_service_conf(additional_config)

        # Write the config-provided SSL certificate, if it exists.
        config_ssl_cert = self.model.config["ssl_cert"]

        if config_ssl_cert != "DEFAULT":
            self.unit.status = MaintenanceStatus("Installing SSL certificate")
            write_ssl_cert(config_ssl_cert)

        # Write the license file, if it exists.
        license_file = self.model.config.get("license_file")
        if license_file:
            self.unit.status = MaintenanceStatus("Writing Landscape license file")
            write_license_file(license_file, self.landscape_uid, self.root_gid)
            self.unit.status = WaitingStatus("Waiting on relations")

        smtp_relay_host = self.model.config.get("smtp_relay_host")
        if smtp_relay_host:
            self.unit.status = MaintenanceStatus("Configuring SMTP relay host")
            self._configure_smtp(smtp_relay_host)

        # Update HAProxy relations, if they exist.
        haproxy_relations = self.model.relations.get("website", [])
        for relation in haproxy_relations:
            self._update_haproxy_connection(relation)

        if any(self.model.config.get(v) for v in OPENID_CONFIG_VALS) and any(
            self.model.config.get(v) for v in OIDC_CONFIG_VALS
        ):
            self.unit.status = BlockedStatus(
                "OpenID and OIDC configurations are mutually exclusive"
            )
        else:
            self._configure_openid()
            self._configure_oidc()

        # Update root_url, if provided
        root_url = self.model.config.get("root_url")
        if root_url:
            update_service_conf(
                {
                    "global": {"root-url": root_url},
                    "api": {"root-url": root_url},
                    "package-upload": {"root-url": root_url},
                }
            )

        config_host = self.model.config.get("db_host")
        schema_password = self.model.config.get("db_schema_password")
        landscape_password = self.model.config.get("db_landscape_password")
        config_port = self.model.config.get("db_port")
        config_user = self.model.config.get("db_schema_user")
        db_kargs = {}
        if config_host:
            db_kargs["host"] = config_host
        if schema_password:
            db_kargs["schema_password"] = schema_password
        if config_port:
            db_kargs["port"] = config_port
        if config_user:
            db_kargs["user"] = config_user
        if landscape_password:
            db_kargs["password"] = landscape_password
        if db_kargs:
            update_db_conf(**db_kargs)
            if self._migrate_schema_bootstrap():
                self.unit.status = WaitingStatus("Waiting on relations")
                self._stored.ready["db"] = True
            else:
                return

        self._bootstrap_account()

        if isinstance(prev_status, BlockedStatus):
            self.unit.status = prev_status

        self._update_ready_status(restart_services=True)

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing apt packages")

        landscape_ppa_key = self.model.config["landscape_ppa_key"]
        if landscape_ppa_key != "":
            try:
                landscape_key_file = apt.import_key(landscape_ppa_key)
                logger.info(f"Imported Landscape PPA key at {landscape_key_file}")
            except apt.GPGKeyError:
                logger.error("Failed to import Landscape PPA key")

        landscape_ppa = self.model.config["landscape_ppa"]

        try:
            # This package is responsible for the hanging installs and ignores env vars
            apt.remove_package(["needrestart"])
            # Add the Landscape Server PPA and install via apt.
            check_call(["add-apt-repository", "-y", landscape_ppa])
            # Explicitly ensure cache is up-to-date after adding the PPA.
            apt.add_package(["landscape-server", "landscape-hashids"], update_cache=True)
            check_call(["apt-mark", "hold", "landscape-hashids"])
        except (PackageNotFoundError, PackageError, CalledProcessError) as exc:
            logger.error("Failed to install packages")
            raise exc  # This will trigger juju's exponential retry

        # Write the config-provided SSL certificate, if it exists.
        config_ssl_cert = self.model.config["ssl_cert"]

        if config_ssl_cert != "DEFAULT":
            self.unit.status = MaintenanceStatus("Installing SSL certificate")
            write_ssl_cert(config_ssl_cert)

        # Write the license file, if it exists.
        license_file = self.model.config.get("license_file")

        if license_file:
            self.unit.status = MaintenanceStatus("Writing Landscape license file")
            write_license_file(license_file, self.landscape_uid, self.root_gid)

        self.unit.status = ActiveStatus("Unit is ready")

        # Indicate that this install is a charm install.
        prepend_default_settings({"DEPLOYED_FROM": "charm"})

        self._update_ready_status()

    def _update_status(self, event: UpdateStatusEvent) -> None:
        """Called at regular intervals by juju."""
        self._update_ready_status()

    def _update_ready_status(self, restart_services=False) -> None:
        """If all relations are prepared, updates unit status to Active."""
        if isinstance(self.unit.status, (BlockedStatus, MaintenanceStatus)):
            return

        if not all(self._stored.ready.values()):
            waiting_on = [rel for rel, ready in self._stored.ready.items() if not ready]
            self.unit.status = WaitingStatus(
                "Waiting on relations: {}".format(", ".join(waiting_on))
            )
            return

        if self._stored.running and not restart_services:
            self.unit.status = ActiveStatus("Unit is ready")
            return

        if self._stored.paused:
            self.unit.status = MaintenanceStatus("Services stopped")
            return

        self._stored.running = self._start_services()

    def _start_services(self) -> bool:
        """
        Starts all Landscape Server systemd services. Returns True if
        successful, False otherwise.
        """
        self.unit.status = MaintenanceStatus("Starting services")
        is_leader = self.unit.is_leader()
        deployment_mode = self.model.config.get("deployment_mode")
        is_standalone = deployment_mode == "standalone"

        update_default_settings(
            {
                "RUN_ALL": "no",
                "RUN_APISERVER": str(self.model.config["worker_counts"]),
                "RUN_ASYNC_FRONTEND": "yes",
                "RUN_JOBHANDLER": "yes",
                "RUN_APPSERVER": str(self.model.config["worker_counts"]),
                "RUN_MSGSERVER": str(self.model.config["worker_counts"]),
                "RUN_PINGSERVER": str(self.model.config["worker_counts"]),
                "RUN_CRON": "yes" if is_leader else "no",
                "RUN_PACKAGESEARCH": "yes" if is_leader else "no",
                "RUN_PACKAGEUPLOADSERVER": "yes"
                if is_leader and is_standalone
                else "no",
                "RUN_PPPA_PROXY": "no",
            }
        )

        logger.info("Starting services")

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

        required_relation_data = ["master", "allowed-units", "port", "user"]
        missing_relation_data = [
            i for i in required_relation_data if i not in unit_data
        ]
        if missing_relation_data:
            logger.info(
                "db relation not yet ready. Missing keys: {}".format(
                    missing_relation_data
                )
            )
            self.unit.status = ActiveStatus("Unit is ready")
            self._update_ready_status()
            return

        allowed_units = unit_data["allowed-units"].split()
        if self.unit.name not in allowed_units:
            logger.info(f"{self.unit.name} not in allowed_units")
            self.unit.status = ActiveStatus("Unit is ready")
            self._update_ready_status()
            return

        self._stored.ready["db"] = False
        self.unit.status = MaintenanceStatus("Setting up databases")

        # We can't use unit_data["host"] because it can return the IP of the secondary
        master = dict(s.split("=", 1) for s in unit_data["master"].split(" "))

        # Override db config if manually set in juju
        config_host = self.model.config.get("db_host")
        if config_host:
            host = config_host
        else:
            host = master["host"]

        landscape_password = self.model.config.get("db_landscape_password")
        if landscape_password:
            password = landscape_password
        else:
            password = master["password"]

        schema_password = self.model.config.get("db_schema_password")

        config_port = self.model.config.get("db_port")
        if config_port:
            port = config_port
        else:
            port = unit_data["port"]
        if not port:
            port = DEFAULT_POSTGRES_PORT  # Fall back to postgres default port if still not set

        config_user = self.model.config.get("db_schema_user")
        if config_user:
            user = config_user
        else:
            user = unit_data["user"]

        update_db_conf(
            host=host,
            port=port,
            user=user,
            password=password,
            schema_password=schema_password,
        )

        if not self._migrate_schema_bootstrap():
            return

        self._stored.ready["db"] = True
        self.unit.status = ActiveStatus("Unit is ready")
        self._update_ready_status()

    def _migrate_schema_bootstrap(self):
        """
        Migrates schema along with the bootstrap command which ensures that the
        databases along with the landscape user exists. In addition creates
        admin if configured. Returns True on success
        """
        try:
            check_call([SCHEMA_SCRIPT, "--bootstrap"])
            self._bootstrap_account()
            return True
        except CalledProcessError as e:
            logger.error(
                "Landscape Server schema update failed with return code %d",
                e.returncode,
            )
            self.unit.status = BlockedStatus("Failed to update database schema")

    def _amqp_relation_joined(self, event: RelationJoinedEvent) -> None:
        self._stored.ready["amqp"] = False
        self.unit.status = MaintenanceStatus("Setting up amqp connection")

        event.relation.data[self.unit].update(
            {
                "username": "landscape",
                "vhost": "landscape",
            }
        )

    def _amqp_relation_changed(self, event):
        unit_data = event.relation.data[event.unit]

        if "password" not in unit_data:
            logger.info("rabbimq-server has not sent password yet")
            return

        hostname = unit_data["hostname"]
        password = unit_data["password"]

        if isinstance(hostname, list):
            hostname = ",".join(hostname)

        update_service_conf(
            {
                "broker": {
                    "host": hostname,
                    "password": password,
                }
            }
        )

        self._stored.ready["amqp"] = True
        self.unit.status = ActiveStatus("Unit is ready")
        self._update_ready_status()

    def _website_relation_joined(self, event: RelationJoinedEvent) -> None:
        self._update_haproxy_connection(event.relation)

        # Update root_url, if not provided.
        if not self.model.config.get("root_url"):
            url = f'https://{event.relation.data[event.unit]["public-address"]}/'
            self._stored.default_root_url = url
            update_service_conf(
                {
                    "global": {"root-url": url},
                    "api": {"root-url": url},
                    "package-upload": {"root-url": url},
                }
            )

        self._update_ready_status()

    def _update_haproxy_connection(self, relation: Relation) -> None:
        self._stored.ready["haproxy"] = False
        self.unit.status = MaintenanceStatus("Setting up haproxy connection")

        # Check the SSL cert stuff first. No sense doing all the other
        # work just to fail here.
        ssl_cert = self.model.config["ssl_cert"]
        ssl_key = self.model.config["ssl_key"]

        if ssl_cert != "DEFAULT" and ssl_key == "":
            # We have a cert but no key, this is an error.
            self.unit.status = BlockedStatus(
                "`ssl_cert` is specified but `ssl_key` is missing"
            )
            return

        if ssl_cert != "DEFAULT":
            try:
                ssl_cert = b64decode(ssl_cert)
                ssl_key = b64decode(ssl_key)
                ssl_cert = b64encode(ssl_cert + b"\n" + ssl_key)
            except binascii.Error:
                self.unit.status = BlockedStatus(
                    "Unable to decode `ssl_cert` or `ssl_key` - must be " "b64-encoded"
                )
                return

        with open(HAPROXY_CONFIG_FILE) as haproxy_config_file:
            haproxy_config = yaml.safe_load(haproxy_config_file)

        http_service = haproxy_config["http_service"]
        https_service = haproxy_config["https_service"]
        https_service["crts"] = [ssl_cert]

        server_ip = relation.data[self.unit]["private-address"]
        unit_name = self.unit.name.replace("/", "-")
        worker_counts = self.model.config["worker_counts"]

        (appservers, pingservers, message_servers, api_servers) = [
            [
                (
                    f"landscape-{name}-{unit_name}-{i}",
                    server_ip,
                    haproxy_config["ports"][name] + i,
                    haproxy_config["server_options"],
                )
                for i in range(worker_counts)
            ]
            for name in ("appserver", "pingserver", "message-server", "api")
        ]

        # There should only ever be one package-upload-server service.
        package_upload_servers = [
            (
                f"landscape-package-upload-{unit_name}-0",
                server_ip,
                haproxy_config["ports"]["package-upload"],
                haproxy_config["server_options"],
            )
        ]

        http_service["servers"] = appservers
        http_service["backends"] = [
            {
                "backend_name": "landscape-ping",
                "servers": pingservers,
            }
        ]
        https_service["servers"] = appservers
        https_service["backends"] = [
            {
                "backend_name": "landscape-message",
                "servers": message_servers,
            },
            {
                "backend_name": "landscape-api",
                "servers": api_servers,
            },
            # Only the leader should have servers for the landscape-package-upload
            # and landscape-hashid-databases backends. However, when the leader
            # is lost, haproxy will fail as the service options will reference
            # a (no longer) existing backend. To prevent that, all units should
            # declare all backends, even if a unit should not have any servers on
            # a specific backend.
            {
                "backend_name": "landscape-package-upload",
                "servers": package_upload_servers if self.unit.is_leader() else [],
            },
            {
                "backend_name": "landscape-hashid-databases",
                "servers": appservers if self.unit.is_leader() else [],
            },
        ]

        error_files_location = haproxy_config["error_files"]["location"]
        error_files = []
        for code, filename in haproxy_config["error_files"]["files"].items():
            error_file_path = os.path.join(error_files_location, filename)
            with open(error_file_path, "rb") as error_file:
                error_files.append(
                    {"http_status": code, "content": b64encode(error_file.read())}
                )

        http_service["error_files"] = error_files
        https_service["error_files"] = error_files

        relation.data[self.unit].update(
            {
                "services": yaml.safe_dump([http_service, https_service]),
            }
        )

        self._stored.ready["haproxy"] = True

        self.unit.status = WaitingStatus("")

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

        self.unit.status = MaintenanceStatus("Configuring HAProxy")
        haproxy_ssl_cert = event.relation.data[event.unit]["ssl_cert"]

        # Sometimes the data has not been encoded propery in the HA charm
        if haproxy_ssl_cert.startswith("b'"):
            haproxy_ssl_cert = haproxy_ssl_cert.strip('b').strip("'")

        if haproxy_ssl_cert != "DEFAULT":
            # If DEFAULT, cert is being managed by a third party,
            # possibly a subordinate charm.
            write_ssl_cert(haproxy_ssl_cert)

        self.unit.status = ActiveStatus("Unit is ready")
        self._update_haproxy_connection(event.relation)

        self._update_ready_status()

    def _website_relation_departed(self, event: RelationDepartedEvent) -> None:
        event.relation.data[self.unit].update({"services": ""})

    def _nrpe_external_master_relation_joined(self, event: RelationJoinedEvent) -> None:
        self._update_nrpe_checks(event.relation)

    def _update_nrpe_checks(self, relation: Relation):
        logger.debug("Configuring NRPE checks")

        if self.unit.is_leader():
            services_to_add = DEFAULT_SERVICES + LEADER_SERVICES
            services_to_remove = ()
        else:
            services_to_add = DEFAULT_SERVICES
            services_to_remove = LEADER_SERVICES

        monitors = {
            "monitors": {
                "remote": {
                    "nrpe": {s: {"command": f"check_{s}"} for s in services_to_add},
                },
            },
        }

        relation.data[self.unit].update(
            {
                "monitors": yaml.safe_dump(monitors),
            }
        )

        if not os.path.exists(NRPE_D_DIR):
            logger.debug("NRPE directories not ready")
            return

        for service in services_to_add:
            service_cfg = service.replace("-", "_")
            cfg_filename = os.path.join(NRPE_D_DIR, f"check_{service_cfg}.cfg")

            if os.path.exists(cfg_filename):
                continue

            with open(cfg_filename, "w") as cfg_fp:
                cfg_fp.write(
                    f"""# check {service}
# The following header was added by the landscape-server charm
# Modifying it will affect nagios monitoring and alerting
# servicegroups: juju
command[check_{service}]=/usr/local/lib/nagios/plugins/check_systemd.py {service}
"""
                )

        for service in services_to_remove:
            service_cfg = service.replace("-", "_")
            cfg_filename = os.path.join(NRPE_D_DIR, f"check_{service_cfg}.cfg")

            if not os.path.exists(cfg_filename):
                continue

            os.remove(cfg_filename)

    def _application_dashboard_relation_joined(self, event: RelationJoinedEvent):
        if not self.unit.is_leader():
            return

        root_url = self.model.config.get("root_url")
        if not root_url:
            root_url = self._stored.default_root_url

        if not root_url:
            root_url = "https://" + str(
                self.model.get_binding(event.relation).network.bind_address
            )

        site_name = self.model.config.get("site_name")
        if site_name:
            subtitle = f"[{site_name}] Systems management"
            group = f"[{site_name}] LMA"
        else:
            subtitle = "Systems management"
            group = "LMA"

        icon_file = f"{self.charm_dir or ''}/icon.svg"
        if os.path.exists(icon_file):
            with open(icon_file) as fp:
                icon_data = fp.read()
        else:
            icon_data = None

        event.relation.data[self.app].update(
            {
                "name": "Landscape",
                "url": root_url,
                "subtitle": subtitle,
                "group": group,
                "icon": icon_data,
            }
        )

    def _leader_elected(self, event: LeaderElectedEvent) -> None:
        # Just because we received this event does not mean we are
        # guaranteed to be the leader by the time we process it. See
        # https://juju.is/docs/sdk/leader-elected-event

        if self.unit.is_leader():
            # Update any nrpe checks.
            peer_relation = self.model.get_relation("replicas")
            ip = str(self.model.get_binding(peer_relation).network.bind_address)
            peer_relation.data[self.app].update({"leader-ip": ip})

            update_service_conf(
                {
                    "package-search": {
                        "host": "localhost",
                    },
                }
            )

        self._leader_changed()

    def _leader_settings_changed(self, event: LeaderSettingsChangedEvent) -> None:
        # Just because we received this event does not mean we are
        # guaranteed to be a follower by the time we process it. See
        # https://juju.is/docs/sdk/leader-elected-event

        if not self.unit.is_leader():
            peer_relation = self.model.get_relation("replicas")
            leader_ip = peer_relation.data[self.app].get("leader-ip")

            if leader_ip:
                update_service_conf(
                    {
                        "package-search": {
                            "host": leader_ip,
                        },
                    }
                )

        self._leader_changed()

    def _leader_changed(self) -> None:
        """
        Generic updates that need to happen whenever leadership changes,
        in both leaders and non-leaders.
        """
        # Update any nrpe checks.
        nrpe_relations = self.model.relations.get("nrpe-external-master", [])

        for relation in nrpe_relations:
            self._update_nrpe_checks(relation)

        if self.unit.is_leader():
            haproxy_relations = self.model.relations.get("website", [])
            for relation in haproxy_relations:
                self._update_haproxy_connection(relation)

        self._update_ready_status(restart_services=True)

    def _on_replicas_relation_joined(self, event: RelationJoinedEvent) -> None:
        if self.unit.is_leader():
            ip = str(self.model.get_binding(event.relation).network.bind_address)
            event.relation.data[self.app].update({"leader-ip": ip})

        event.relation.data[self.unit].update({"unit-data": self.unit.name})

    def _on_replicas_relation_changed(self, event: RelationChangedEvent) -> None:
        leader_ip_value = event.relation.data[self.app].get("leader-ip")

        if leader_ip_value and leader_ip_value != self._stored.leader_ip:
            self._stored.leader_ip = leader_ip_value

        if self.unit.is_leader():
            haproxy_relations = self.model.relations.get("website", [])
            for relation in haproxy_relations:
                self._update_haproxy_connection(relation)

    def _configure_smtp(self, relay_host: str) -> None:

        # Rewrite postfix config.
        with open(POSTFIX_CF, "r") as postfix_config_file:
            new_lines = []
            for line in postfix_config_file:
                if line.startswith("relayhost ="):
                    new_line = "relayhost = " + relay_host
                else:
                    new_line = line

                new_lines.append(new_line)

        with open(POSTFIX_CF, "w") as postfix_config_file:
            postfix_config_file.write("\n".join(new_lines))

        # Restart postfix.
        if not service_reload("postfix"):
            self.unit.status = BlockedStatus("postfix configuration failed")
        else:
            self.unit.status = WaitingStatus("Waiting on relations")

    def _configure_oidc(self) -> None:
        self.unit.status = MaintenanceStatus("Configuring OIDC")

        oidc_issuer = self.model.config.get("oidc_issuer")
        oidc_client_id = self.model.config.get("oidc_client_id")
        oidc_client_secret = self.model.config.get("oidc_client_secret")
        oidc_logout_url = self.model.config.get("oidc_logout_url")
        oidc_vals = (oidc_issuer, oidc_client_id, oidc_client_secret, oidc_logout_url)
        none_count = oidc_vals.count(None)

        if none_count == 0:
            update_service_conf(
                {
                    "landscape": {
                        "oidc-issuer": oidc_issuer,
                        "oidc-client-id": oidc_client_id,
                        "oidc-client-secret": oidc_client_secret,
                        "oidc-logout-url": oidc_logout_url,
                    },
                }
            )
        elif none_count == 1 and oidc_logout_url is None:
            # Only the logout url is optional.
            update_service_conf(
                {
                    "landscape": {
                        "oidc-issuer": oidc_issuer,
                        "oidc-client-id": oidc_client_id,
                        "oidc-client-secret": oidc_client_secret,
                    },
                }
            )
        elif none_count < 4:
            self.unit.status = BlockedStatus(
                "OIDC connect config requires at least 'oidc_issuer', "
                "'oidc_client_id', and 'oidc_client_secret' values"
            )
            return

        self.unit.status = WaitingStatus("Waiting on relations")

    def _configure_openid(self) -> None:
        self.unit.status = MaintenanceStatus("Configuring OpenID")

        openid_provider_url = self.model.config.get("openid_provider_url")
        openid_logout_url = self.model.config.get("openid_logout_url")

        if openid_provider_url and openid_logout_url:
            update_service_conf(
                {
                    "landscape": {
                        "openid-provider-url": openid_provider_url,
                        "openid-logout-url": openid_logout_url,
                    },
                }
            )
            self.unit.status = WaitingStatus("Waiting on relations")
        elif openid_provider_url or openid_logout_url:
            self.unit.status = BlockedStatus(
                "OpenID configuration requires both 'openid_provider_url' and "
                "'openid_logout_url'"
            )

    def _bootstrap_account(self):
        """If admin account details are provided, create admin"""
        if not self.unit.is_leader():
            return
        if self._stored.account_bootstrapped:  # Admin already created
            return
        karg = {}  # Keyword args for command line
        karg["admin_email"] = self.model.config.get("admin_email")
        karg["admin_name"] = self.model.config.get("admin_name")
        karg["admin_password"] = self.model.config.get("admin_password")
        required_args = karg.values()
        if not any(required_args):  # Return since no args are specified
            return
        if not all(required_args):  # Some required args are missing
            logger.error(
                "Admin email, name, and password required for bootstrap account"
            )
            return
        karg["root_url"] = self.model.config.get("root_url")
        if not karg["root_url"]:
            default_root_url = self._stored.default_root_url
            if default_root_url:
                karg["root_url"] = default_root_url
            else:
                logger.error("Bootstrap account waiting on default root url..")
                return
        karg["registration_key"] = self.model.config.get("registration_key")
        karg["system_email"] = self.model.config.get("system_email")

        # Collect command line arguments
        args = [BOOTSTRAP_ACCOUNT_SCRIPT]
        for key, value in karg.items():
            if not value:
                continue
            args.append("--" + key)
            args.append(value)

        try:
            logger.info(args)
            result = subprocess.run(args, capture_output=True, text=True)
        except FileNotFoundError:
            logger.error("Bootstrap script not found!")
            logger.error(BOOTSTRAP_ACCOUNT_SCRIPT)
            return
        logger.info(result.stdout)
        if result.returncode:
            if "DuplicateAccountError" in result.stderr:
                logger.error("Cannot bootstrap b/c account is already there!")
                self._stored.account_bootstrapped = True
            else:
                logger.error(result.stderr)
        else:
            logger.info("Admin account successfully bootstrapped!")
            self._stored.account_bootstrapped = True

    def _pause(self, event: ActionEvent) -> None:
        self.unit.status = MaintenanceStatus("Stopping services")
        event.log("Stopping services")

        try:
            check_call([LSCTL, "stop"])
        except CalledProcessError as e:
            logger.error("Stopping services failed with return code %d", e.returncode)
            self.unit.status = BlockedStatus("Failed to stop services")
            event.fail("Failed to stop services")
        else:
            self.unit.status = MaintenanceStatus("Services stopped")
            self._stored.running = False
            self._stored.paused = True

    def _resume(self, event: ActionEvent):
        self.unit.status = MaintenanceStatus("Starting services")
        event.log("Starting services")

        start_result = subprocess.run([LSCTL, "start"], capture_output=True, text=True)

        try:
            check_call([LSCTL, "status"])
        except CalledProcessError as e:
            logger.error("Starting services failed with return code %d", e.returncode)
            logger.error("Failed to start services: %s", start_result.stdout)
            self.unit.status = MaintenanceStatus("Stopping services")
            subprocess.run([LSCTL, "stop"])
            self.unit.status = BlockedStatus("Failed to start services")
            event.fail("Failed to start services: %s", start_result.stdout)
        else:
            self._stored.running = True
            self._stored.paused = False
            self.unit.status = ActiveStatus("Unit is ready")
            self._update_ready_status()

    def _upgrade(self, event: ActionEvent) -> None:
        if self._stored.running:
            event.fail(
                "Cannot upgrade while running. Please run action "
                "'pause' prior to upgrade"
            )
            return

        prev_status = self.unit.status
        self.unit.status = MaintenanceStatus("Upgrading packages")
        event.log("Upgrading Landscape packages...")

        apt.update()

        for package in LANDSCAPE_PACKAGES:
            try:
                event.log(f"Upgrading {package}...")
                pkg = apt.DebianPackage.from_apt_cache(package)
                pkg.ensure(state=apt.PackageState.Latest)
                installed = apt.DebianPackage.from_installed_package(package)
                event.log(f"Upgraded to {installed.version}...")
            except PackageNotFoundError as e:
                logger.error(
                    f"Could not upgrade package {package}. Reason: {e.message}"
                )
                event.fail(f"Could not upgrade package {package}. Reason: {e.message}")
                self.unit.status = BlockedStatus("Failed to upgrade packages")
                return

        self.unit.status = prev_status

    def _migrate_schema(self, event: ActionEvent) -> None:
        if self._stored.running:
            event.fail(
                "Cannot migrate schema while running. Please run action"
                " 'pause' prior to migration"
            )
            return

        prev_status = self.unit.status
        self.unit.status = MaintenanceStatus("Migrating schemas...")
        event.log("Running schema migration...")

        try:
            subprocess.run([SCHEMA_SCRIPT], check=True, text=True)
        except CalledProcessError as e:
            logger.error("Schema migration failed with error code %s", e.returncode)
            event.fail("Schema migration failed with error code %s", e.returncode)
            self.unit.status = BlockedStatus("Failed schema migration")
        else:
            self.unit.status = prev_status

    def _hash_id_databases(self, event: ActionEvent) -> None:
        prev_status = self.unit.status
        self.unit.status = MaintenanceStatus("Hashing ID databases...")
        event.log("Running hash_id_databases")

        try:
            subprocess.run(
                ["sudo", "-u", "landscape", HASH_ID_DATABASES], check=True, text=True
            )
        except CalledProcessError as e:
            logger.error("Hashing ID databases failed with error code %s", e.returncode)
            event.fail("Hashing ID databases failed with error code %s", e.returncode)
        finally:
            self.unit.status = prev_status


if __name__ == "__main__":  # pragma: no cover
    main(LandscapeServerCharm)
