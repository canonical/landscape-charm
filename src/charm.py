#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charm the service.

Refer to the following post for a quick-start guide that will help you
develop a new k8s charm using the Operator Framework:

    https://discourse.charmhub.io/t/4208
"""

from dataclasses import asdict
from functools import cached_property
import os
import subprocess
from subprocess import CalledProcessError, check_call
from typing import List
from urllib.parse import urlparse

from charmlibs.interfaces.tls_certificates import (
    CertificateRequestAttributes,
    Mode,
    TLSCertificatesRequiresV4,
)
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_agent.v0.cos_agent import COSAgentProvider
from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError
from charms.operator_libs_linux.v0.passwd import group_exists, user_exists
from charms.operator_libs_linux.v1.systemd import (
    service_pause,
    service_reload,
    service_resume,
    service_running,
    SystemdError,
)
from ops import main
from ops.charm import (
    ActionEvent,
    CharmBase,
    InstallEvent,
    LeaderElectedEvent,
    LeaderSettingsChangedEvent,
    RelationChangedEvent,
    RelationJoinedEvent,
    UpdateStatusEvent,
    UpgradeCharmEvent,
)
from ops.framework import StoredState
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    WaitingStatus,
)
from pydantic import BaseModel, IPvAnyAddress, ValidationError
import yaml

from config import DEFAULT_CONFIGURATION, LandscapeCharmConfiguration
from database import (
    DatabaseConnectionContext,
    fetch_postgres_relation_data,
    grant_role,
)
import haproxy
from helpers import get_modified_env_vars, logger, migrate_service_conf
from settings_files import (
    AMQP_USERNAME,
    configure_for_deployment_mode,
    DEFAULT_POSTGRES_PORT,
    generate_cookie_encryption_key,
    generate_secret_token,
    get_postgres_roles,
    merge_service_conf,
    prepend_default_settings,
    update_db_conf,
    update_default_settings,
    update_service_conf,
    VHOSTS,
    write_license_file,
)

DEBCONF_SET_SELECTIONS = "/usr/bin/debconf-set-selections"
DPKG_RECONFIGURE = "/usr/sbin/dpkg-reconfigure"
LSCTL = "/usr/bin/lsctl"
NRPE_D_DIR = "/etc/nagios/nrpe.d"
POSTFIX_CF = "/etc/postfix/main.cf"
SCHEMA_SCRIPT = "/usr/bin/landscape-schema"
BOOTSTRAP_ACCOUNT_SCRIPT = "/opt/canonical/landscape/bootstrap-account"
AUTOREGISTRATION_SCRIPT = os.path.join(os.path.dirname(__file__), "autoregistration.py")
HASH_ID_DATABASES = "/opt/canonical/landscape/hash-id-databases-ignore-maintenance"
UPDATE_WSL_DISTRIBUTIONS_SCRIPT = "/opt/canonical/landscape/update-wsl-distributions"
LANDSCAPE_ERROR_FILES_DIR = "/opt/canonical/landscape/canonical/landscape/offline"

LANDSCAPE_SERVER = "landscape-server"
LANDSCAPE_PACKAGES = (
    LANDSCAPE_SERVER,
    "landscape-client",
    "landscape-common",
)
LANDSCAPE_UBUNTU_INSTALLER_ATTACH = "landscape-ubuntu-installer-attach"

DEFAULT_SERVICES = (
    "landscape-api",
    "landscape-appserver",
    "landscape-async-frontend",
    "landscape-job-handler",
    "landscape-msgserver",
    "landscape-pingserver",
    "landscape-hostagent-messenger",
    "landscape-hostagent-consumer",
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

PROXY_ENV_MAPPING = {
    "JUJU_CHARM_HTTP_PROXY": "--with-http-proxy",
    "JUJU_CHARM_HTTPS_PROXY": "--with-https-proxy",
    "JUJU_CHARM_NO_PROXY": "--with-no-proxy",
}

METRIC_INSTRUMENTED_SERVICE_PORTS = [
    ("appserver", 8080),
    ("pingserver", 8070),
    ("message-server", 8090),
    ("api", 9080),
    ("package-upload", 9100),
    ("package-search", 9099),
]
"""
Default ports for Landscape services in a self-hosted deployment.

Currently this var is only used for metrics configuration, so it only includes the
applicable services.

TODO all service configuration should be configurable through Juju and passed to the
Landscape server configuration file.
"""

METRICS_RULES_DIR = os.path.join(os.path.dirname(__file__), "prometheus_alert_rules")
"""The location of Prometheus metrics alerts rules for the COS relation."""


def get_args_with_secrets_removed(args, arg_names):
    """
    We log args passed in the command line. But we want to remove secrets.

    Returns a copy of the args passed in with secrets associated with arg_names
    redacted.
    """
    args = args.copy()
    for arg_name in arg_names:
        dash_arg_name = "--" + arg_name
        if dash_arg_name in args:
            idx = args.index(dash_arg_name) + 1
            if idx < len(args):
                args[idx] = "REDACTED"
    return args


class PeerIPs(BaseModel):
    all_ips: list[IPvAnyAddress]
    leader_ip: IPvAnyAddress


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
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)

        # Modern Postgres relation
        if self.model.get_relation("database") is not None:
            self.database = DatabaseRequires(
                self,
                relation_name="database",
                database_name="database",
                extra_user_roles="SUPERUSER",
            )
            self.framework.observe(
                self.database.on.database_created, self._database_relation_changed
            )
            self.framework.observe(
                self.database.on.endpoints_changed, self._database_relation_changed
            )

        # Legacy Postgres relation
        elif self.model.get_relation("db") is not None:
            logger.warning(
                "The legacy `db` endpoint is deprecated and support will be "
                "dropped in a future release. Please rename the relation "
                "endpoint to 'database'."
            )
            self.framework.observe(
                self.on.db_relation_joined, self._db_relation_changed
            )
            self.framework.observe(
                self.on.db_relation_changed, self._db_relation_changed
            )

        # Inbound vhost
        self.framework.observe(
            self.on.inbound_amqp_relation_joined, self._amqp_relation_joined
        )
        self.framework.observe(
            self.on.inbound_amqp_relation_changed, self._amqp_relation_changed
        )

        # Outbound
        self.framework.observe(
            self.on.outbound_amqp_relation_joined, self._amqp_relation_joined
        )
        self.framework.observe(
            self.on.outbound_amqp_relation_changed, self._amqp_relation_changed
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
        self.framework.observe(
            self.on.load_balancer_certificates_relation_changed,
            self._on_lb_certs_changed,
        )
        self.framework.observe(
            self.on.load_balancer_certificates_relation_joined,
            self._on_lb_certs_changed,
        )

        # Actions
        self.framework.observe(self.on.pause_action, self._pause)
        self.framework.observe(self.on.resume_action, self._resume)
        self.framework.observe(self.on.upgrade_action, self._upgrade)
        self.framework.observe(self.on.migrate_schema_action, self._migrate_schema)
        self.framework.observe(
            self.on.hash_id_databases_action, self._hash_id_databases
        )
        self.framework.observe(
            self.on.migrate_service_conf_action, self._migrate_service_conf
        )
        self.framework.observe(
            self.on.get_certificates_action, self._on_get_certificates_action
        )

        # State
        self._stored.set_default(
            ready={
                "db": False,
                "inbound-amqp": False,
                "outbound-amqp": False,
                "load-balancer-certificates": False,
            }
        )
        self._stored.set_default(leader_ip="")
        self._stored.set_default(running=False)
        self._stored.set_default(paused=False)
        self._stored.set_default(default_root_url="")
        self._stored.set_default(account_bootstrapped=False)
        self._stored.set_default(secret_token=None)
        self._stored.set_default(cookie_encryption_key=None)
        self._stored.set_default(enable_ubuntu_installer_attach=False)
        self._stored.set_default(haproxy_config={})

        self.root_gid = group_exists("root").gr_gid

        self._grafana_agent = COSAgentProvider(
            self,
            scrape_configs=self._generate_scrape_configs,
            metrics_rules_dir=METRICS_RULES_DIR,
            refresh_events=[
                self.on.config_changed,
                self.on.upgrade_charm,
            ],
        )
        try:
            self.charm_config = LandscapeCharmConfiguration.validate(self.model.config)
        except ValidationError as e:
            logger.error(f"Invalid configuration: {e.errors()}")
            self.charm_config = DEFAULT_CONFIGURATION
            self.unit.status = BlockedStatus(
                "Invalid configuration. See `juju debug-log`."
            )

        self.lb_certificates = TLSCertificatesRequiresV4(
            charm=self,
            relationship_name="load-balancer-certificates",
            certificate_requests=(
                [self._get_certificate_request_attributes()]
                if self._get_certificate_request_attributes()
                else []
            ),
            mode=Mode.UNIT,
            refresh_events=[
                self.on.config_changed,
                self.on.replicas_relation_changed,
                self.on.replicas_relation_joined,
                self.on.leader_elected,
                self.on.leader_settings_changed,
                self.on.upgrade_charm,
            ],
        )

    def _get_certificate_request_attributes(
        self,
    ) -> CertificateRequestAttributes | None:
        unit_ip = self.unit_ip
        if not unit_ip:
            return None

        hostname = None
        if self.charm_config.root_url:
            parsed = urlparse(self.charm_config.root_url)
            if parsed.hostname:
                hostname = parsed.hostname

        return CertificateRequestAttributes(
            common_name=hostname or unit_ip,
            sans_ip=[unit_ip],
            sans_dns=[hostname] if hostname else None,
        )

    @property
    def peer_ips(self) -> PeerIPs | None:
        unit_ip = self.unit_ip
        if not unit_ip:
            return None

        all_ips = [unit_ip]
        leader_ip = unit_ip

        if replicas := self.model.get_relation("replicas"):
            leader_ip = replicas.data[self.app].get("leader-ip", unit_ip)

            for unit in replicas.units:
                # NOTE: Replicas does not contain this unit
                if peer_unit_address := replicas.data[unit].get("private-address"):
                    all_ips.append(peer_unit_address)

        peer_ips = PeerIPs(all_ips=all_ips, leader_ip=leader_ip)

        return peer_ips

    @property
    def unit_ip(self) -> str | None:
        network_binding = self.model.get_binding("replicas")
        if network_binding is None:
            return None

        try:
            bind_address = network_binding.network.bind_address
        except ModelError as e:
            logger.warning(f"No bind address found for `replicas`: {str(e)}")
            return None

        return str(bind_address) if bind_address else None

    def _generate_scrape_configs(self) -> list[dict]:
        """
        Return a scrape config for every metric-instrumented Landscape service.
        """
        return [
            {
                "scrape_interval": self.charm_config.prometheus_scrape_interval,
                "metrics_path": "/metrics",
                "static_configs": [
                    {
                        "targets": [f"localhost:{port}"],
                        "labels": {"landscape_service": f"{service}"},
                    },
                ],
            }
            for service, port in METRIC_INSTRUMENTED_SERVICE_PORTS
        ]

    def _on_config_changed(self, _) -> None:
        """
        Handle configuration changes.
        """
        try:
            self.charm_config = LandscapeCharmConfiguration.validate(self.model.config)
            self.unit.status = WaitingStatus("Configuration validated...")
        except ValidationError as e:
            logger.error(f"Invalid configuration: {e.errors()}")
            self.unit.status = BlockedStatus(
                "Invalid configuration. See `juju debug-log`."
            )
            return

        try:
            self._configure_ubuntu_installer_attach(
                self.charm_config.enable_ubuntu_installer_attach
            )
        except PackageError as e:
            # TODO Should be "blocked" eventually, but this causes the charm to be
            # stuck in the "blocked" state permanently.
            self.unit.status = MaintenanceStatus(
                "Failed to enable `landscape-ubuntu-installer-attach`. "
                "See `juju debug-log`."
            )
            logger.exception(e)
            return

        # Update additional configuration
        update_service_conf(
            {"global": {"deployment-mode": self.charm_config.deployment_mode}}
        )
        configure_for_deployment_mode(self.charm_config.deployment_mode)

        if self.charm_config.additional_service_config:
            merge_service_conf(self.charm_config.additional_service_config)

        if self.charm_config.license_file:
            self.unit.status = MaintenanceStatus("Writing Landscape license file")
            write_license_file(
                self.charm_config.license_file,
                user_exists("landscape").pw_uid,
                self.root_gid,
            )
            self.unit.status = WaitingStatus("Waiting on relations")

        if self.charm_config.smtp_relay_host:
            self.unit.status = MaintenanceStatus("Configuring SMTP relay host")
            self._configure_smtp(self.charm_config.smtp_relay_host)

        self._configure_openid()
        self._configure_oidc()

        service_conf_updates = {
            service: {"workers": str(self.charm_config.worker_counts)}
            for service in ("landscape", "api", "message-server", "pingserver")
        }

        if root_url := self.charm_config.root_url:
            service_conf_updates["global"] = {"root-url": root_url}
            service_conf_updates["api"]["root-url"] = root_url
            service_conf_updates["package-upload"] = {"root-url": root_url}

        update_service_conf(service_conf_updates)

        db_kargs = {}
        if config_host := self.charm_config.db_host:
            db_kargs["host"] = config_host
        if schema_password := self.charm_config.db_schema_password:
            db_kargs["schema_password"] = schema_password
        if config_port := self.charm_config.db_port:
            db_kargs["port"] = config_port
        if config_user := self.charm_config.db_schema_user:
            db_kargs["user"] = config_user
        if landscape_password := self.charm_config.db_landscape_password:
            db_kargs["password"] = landscape_password
        if db_kargs:
            update_db_conf(**db_kargs)
            if self._migrate_schema_bootstrap():
                self.unit.status = WaitingStatus("Waiting on relations")
                self._stored.ready["db"] = True
            else:
                return

        self._bootstrap_account()
        self._set_autoregistration()

        secret_token = self._get_secret_token()
        cookie_encryption_key = self._get_cookie_encryption_key()
        if self.unit.is_leader():
            if not secret_token:
                # If the secret token wasn't in the config, and we don't have one
                # in the peer relation data, then the leader needs to generate one
                # for all of the units to use.
                logger.info("Generating new random secret token")
                secret_token = generate_secret_token()
                peer_relation = self.model.get_relation("replicas")
                peer_relation.data[self.app].update({"secret-token": secret_token})

            if not cookie_encryption_key:
                logger.info("Generating new random cookie encryption key")
                cookie_encryption_key = generate_cookie_encryption_key()
                peer_relation = self.model.get_relation("replicas")
                peer_relation.data[self.app].update(
                    {"cookie-encryption-key": cookie_encryption_key}
                )

        if (secret_token) and (secret_token != self._stored.secret_token):
            self._write_secret_token(secret_token)
            self._stored.secret_token = secret_token

        if (cookie_encryption_key) and (
            cookie_encryption_key != self._stored.cookie_encryption_key
        ):
            self._write_cookie_encryption_key(cookie_encryption_key)
            self._stored.cookie_encryption_key = cookie_encryption_key

        self._update_haproxy()
        self._update_ready_status(restart_services=True)

    def _get_secret_token(self) -> str | None:
        """
        Get the `secret-token` config from either the juju config for this unit, or from
        app data in the replica relation.

        If set on neither, return `None`.
        """
        secret_token = self.charm_config.secret_token
        if not secret_token:
            peer_relation = self.model.get_relation("replicas")
            if peer_relation is not None:
                secret_token = peer_relation.data[self.app].get("secret-token", None)
            else:
                secret_token = None
        return secret_token

    def _get_cookie_encryption_key(self):
        cookie_encryption_key = self.charm_config.cookie_encryption_key
        if not cookie_encryption_key:
            peer_relation = self.model.get_relation("replicas")
            if peer_relation is not None:
                cookie_encryption_key = peer_relation.data[self.app].get(
                    "cookie-encryption-key", None
                )
            else:
                cookie_encryption_key = None
        return cookie_encryption_key

    def _write_secret_token(self, secret_token):
        logger.info("Writing secret token")
        update_service_conf({"landscape": {"secret-token": secret_token}})

    def _write_cookie_encryption_key(self, cookie_encryption_key):
        logger.info("Writing cookie encryption key")
        update_service_conf({"api": {"cookie-encryption-key": cookie_encryption_key}})

    def _ensure_haproxy_installed(self) -> None:
        try:
            apt.DebianPackage.from_installed_package(haproxy.HAPROXY_APT_PACKAGE_NAME)
            logger.debug("HAProxy is already installed")
        except PackageNotFoundError:
            logger.info("HAProxy not installed, installing...")
            self.unit.status = MaintenanceStatus("Installing HAProxy...")

            try:
                haproxy.install()
            except haproxy.HAProxyError as e:
                logger.error("Failed to install HAProxy: %s", str(e))
                raise e

            try:
                haproxy.copy_error_files_from_source(LANDSCAPE_ERROR_FILES_DIR)
                logger.debug("HAProxy error files copied")
            except haproxy.HAProxyError as e:
                logger.error("Failed to copy HAProxy error files: %s", str(e))
                raise e

    def _on_lb_certs_changed(
        self, _: RelationChangedEvent | RelationJoinedEvent
    ) -> None:
        self._update_haproxy()

    def _on_upgrade_charm(self, _: UpgradeCharmEvent) -> None:
        self._update_haproxy()

    def _on_install(self, event: InstallEvent) -> None:
        """Handle the install event."""
        self.unit.status = MaintenanceStatus("Installing apt packages")

        landscape_ppa_key = self.charm_config.landscape_ppa_key
        if landscape_ppa_key != "":
            try:
                landscape_key_file = apt.import_key(landscape_ppa_key)
                logger.info(f"Imported Landscape PPA key at {landscape_key_file}")
            except apt.GPGKeyError:
                logger.error("Failed to import Landscape PPA key")

        landscape_ppa = self.charm_config.landscape_ppa

        try:
            # This package is responsible for the hanging installs and ignores env vars
            apt.remove_package(["needrestart"])

            # Add the Landscape Server PPA and install via apt.
            # add-apt-repository doesn't use the proxy configuration from apt or juju
            # let's make sure to use the http(s) proxy settings from the charm or at
            # least any juju_proxy setting, add the classic http(s)_proxy to the env
            # that will be used only for add-apt-repository call
            add_apt_repository_env = os.environ.copy()
            for proxy_var, proxy_var_value in [
                ("http_proxy", self.charm_config.http_proxy),
                ("https_proxy", self.charm_config.https_proxy),
            ]:
                juju_proxy_var = f"JUJU_CHARM_{proxy_var.upper()}"

                # if the charm has a proxy conf configured, override juju_http(s)
                # configuration
                if proxy_var_value:
                    add_apt_repository_env[proxy_var] = proxy_var_value
                elif juju_proxy_var in add_apt_repository_env:
                    add_apt_repository_env[proxy_var] = add_apt_repository_env[
                        juju_proxy_var
                    ]

                if proxy_var in add_apt_repository_env:
                    logger.info(
                        f"add-apt-repository {proxy_var} variable set to : "
                        f"{add_apt_repository_env[proxy_var]}"
                    )

            # juju_no_proxy is not perfectly compatible with Shell environment
            # let's handle only the no_proxy from the charm's configuration
            if self.charm_config.no_proxy:
                add_apt_repository_env["no_proxy"] = self.charm_config.no_proxy
                logger.info(
                    f"add-apt-repository no_proxy variable set to : "
                    f"{add_apt_repository_env['no_proxy']}"
                )

            check_call(
                ["add-apt-repository", "-y", landscape_ppa], env=add_apt_repository_env
            )

            if self.charm_config.min_install:
                logger.info("Not installing hashids..")
                check_call(
                    [
                        "apt",
                        "install",
                        LANDSCAPE_SERVER,
                        "--no-install-recommends",
                        "-y",
                    ]
                )
            else:
                # Explicitly ensure cache is up-to-date after adding the PPA.
                apt.add_package(
                    [LANDSCAPE_SERVER, "landscape-hashids"], update_cache=True
                )
                check_call(["apt-mark", "hold", "landscape-hashids"])
            check_call(["apt-mark", "hold", LANDSCAPE_SERVER])
        except (PackageNotFoundError, PackageError, CalledProcessError) as exc:
            logger.error("Failed to install packages")
            raise exc  # This will trigger juju's exponential retry

        # Write the license file, if it exists.
        license_file = self.charm_config.license_file

        if license_file:
            self.unit.status = MaintenanceStatus("Writing Landscape license file")
            write_license_file(
                license_file, user_exists("landscape").pw_uid, self.root_gid
            )

        self._ensure_haproxy_installed()

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
        deployment_mode = self.charm_config.deployment_mode
        is_standalone = deployment_mode == "standalone"

        update_default_settings(
            {
                "RUN_ALL": "no",
                "RUN_APISERVER": str(self.charm_config.worker_counts),
                "RUN_ASYNC_FRONTEND": "yes",
                "RUN_JOBHANDLER": "yes",
                "RUN_APPSERVER": str(self.charm_config.worker_counts),
                "RUN_MSGSERVER": str(self.charm_config.worker_counts),
                "RUN_PINGSERVER": str(self.charm_config.worker_counts),
                "RUN_CRON": "yes" if is_leader else "no",
                "RUN_PACKAGESEARCH": "yes" if is_leader else "no",
                "RUN_PACKAGEUPLOADSERVER": (
                    "yes" if is_leader and is_standalone else "no"
                ),
                "RUN_PPPA_PROXY": "no",
            }
        )

        logger.info("Starting services")

        try:
            check_call([LSCTL, "restart"], env=get_modified_env_vars())
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
        config_host = self.charm_config.db_host
        if config_host:
            host = config_host
        else:
            host = master["host"]

        landscape_password = self.charm_config.db_landscape_password
        if landscape_password:
            password = landscape_password
        else:
            password = master["password"]

        schema_password = self.charm_config.db_schema_password

        config_port = self.charm_config.db_port
        if config_port:
            port = config_port
        else:
            port = unit_data["port"]
        if not port:
            port = DEFAULT_POSTGRES_PORT  # Fall back to postgres default port

        config_user = self.charm_config.db_schema_user
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

        if not self._update_wsl_distributions():
            return

        self._stored.ready["db"] = True
        self.unit.status = ActiveStatus("Unit is ready")
        self._update_ready_status(restart_services=True)

    def _database_relation_changed(
        self, _: DatabaseCreatedEvent | DatabaseEndpointsChangedEvent
    ) -> None:
        """
        Handle the modern Postgres charm interface (`database` relation).
        """
        db_ctx: DatabaseConnectionContext = fetch_postgres_relation_data(
            db_manager=self.database
        )

        required_fields = ["username", "password", "port", "host"]
        missing_fields = [f for f in required_fields if not asdict(db_ctx).get(f)]
        if missing_fields:
            logger.info(
                f"Missing required database fields: {', '.join(missing_fields)}"
            )

            self._stored.ready["db"] = False
            self.unit.status = ActiveStatus("Unit is ready")
            self._update_ready_status()
            return

        self._stored.ready["db"] = False
        self.unit.status = MaintenanceStatus("Setting up databases")

        relation_username = db_ctx.username
        relation_password = db_ctx.password

        config_host = self.model.config.get("db_host")
        if config_host:
            host = config_host
            logger.debug("Using the host from the config: %s", host)
        else:
            host = db_ctx.host
            logger.debug("Using the `host` from the `database` relation: %s", host)

        landscape_password = self.model.config.get("db_landscape_password")
        if landscape_password:
            password = landscape_password
            logger.debug("Using the password from the config.")
        else:
            password = db_ctx.password
            logger.debug("Using the password from the `database` relation.")

        schema_password = self.model.config.get("db_schema_password")

        config_port = self.model.config.get("db_port")
        if config_port:
            port = config_port
            logger.debug("Using the port provided in the config: %s", port)
        else:
            port = db_ctx.port
            logger.debug("Using the port provided by the `database` relation: %s", port)
        if not port:
            port = DEFAULT_POSTGRES_PORT  # Fall back to postgres default port
            logger.info("Using the default Postgres port: %d", DEFAULT_POSTGRES_PORT)

        config_user = self.model.config.get("db_schema_user")
        if config_user:
            user = config_user
            logger.debug("Using the username provided in the config.")
        else:
            user = db_ctx.username
            logger.debug("Using the username provided by the relation.")

        logger.debug("Updating the `stores` and `schema` sections in `service.conf`...")

        update_db_conf(
            host=host,
            port=port,
            user=user,
            password=password,
            schema_password=schema_password,
        )

        if not self.unit.is_leader():
            self._stored.ready["db"] = True
            self.unit.status = ActiveStatus("Unit is ready")
            self._update_ready_status(restart_services=True)
            return

        roles = get_postgres_roles(db_ctx.version)

        if not self._migrate_schema_bootstrap(roles.owner):
            logger.error(
                "Migrating schema failed trying to update the `database` relation!"
            )
            return

        supports_charmed_roles = roles.owner == "charmed_dba"

        if supports_charmed_roles:
            grant_role(
                host=host,
                port=port,
                relation_user=relation_username,
                relation_password=relation_password,
                role="charmed_dml",
                user=roles.application,
            )

            if roles.superuser:
                grant_role(
                    host=host,
                    port=port,
                    relation_user=relation_username,
                    relation_password=relation_password,
                    role="charmed_dba",
                    user=roles.superuser,
                )

        if not self._update_wsl_distributions():
            logger.info(
                "Updating WSL distributions failed trying to update the `database` "
                "relation!"
            )
            return

        logger.info("Set up complete!")
        self._stored.ready["db"] = True
        self.unit.status = ActiveStatus("Unit is ready")

        self._update_ready_status(restart_services=True)

    @cached_property
    def _proxy_settings(self) -> List[str]:
        """Determines the current proxy settings from the juju-related environment
        variables.

        :returns: A list of proxy settings arguments suitable for passing to
            `SCHEMA_SCRIPT`.
        """
        settings = []

        for juju_env_var, schema_arg_name in PROXY_ENV_MAPPING.items():
            value = os.environ.get(juju_env_var)

            if value:
                settings.append(schema_arg_name)
                settings.append(value)

        return settings

    def _migrate_schema_bootstrap(self, owner_role: str | None = None):
        """
        Migrates schema along with the bootstrap command which ensures that the
        databases and the landscape user exists, and that proxy settings are set.
        In addition, creates admin if configured.

        :returns: True on success.
        """
        call = [SCHEMA_SCRIPT, "--bootstrap"]

        if owner_role:
            call.extend(["--db-owner-role", owner_role])

        if self._proxy_settings:
            call.extend(self._proxy_settings)

        try:
            check_call(call, env=get_modified_env_vars())
            self._bootstrap_account()
            self._set_autoregistration()
            return True
        except CalledProcessError as e:
            logger.error(
                "Landscape Server schema update failed with return code %d",
                e.returncode,
            )
            self.unit.status = BlockedStatus("Failed to update database schema")

    def _update_wsl_distributions(self) -> bool | None:
        logger.info("Updating WSL distributions...")

        try:
            check_call(
                [UPDATE_WSL_DISTRIBUTIONS_SCRIPT],
                env=get_modified_env_vars(),
            )
            return True
        except CalledProcessError as e:
            logger.error(
                "Failed to update WSL distributions with return code %d", e.returncode
            )
            logger.info(
                "Try updating the stock WSL distributions again later by running '%s'.",
                UPDATE_WSL_DISTRIBUTIONS_SCRIPT,
            )

    def _amqp_relation_joined(self, event: RelationJoinedEvent) -> None:
        relation_name = event.relation.name
        self._stored.ready[relation_name] = False
        self.unit.status = MaintenanceStatus(f"Setting up {relation_name} connection")

        event.relation.data[self.unit].update(
            {
                "username": AMQP_USERNAME,
                "vhost": VHOSTS[relation_name],
            }
        )

    def _amqp_relation_changed(self, event):
        unit_data = event.relation.data[event.unit]
        relation_name = event.relation.name

        if "password" not in unit_data:
            logger.info("rabbitmq-server has not sent password yet")
            return

        hostname = unit_data["hostname"]
        password = unit_data["password"]

        if isinstance(hostname, list):
            hostname = ",".join(hostname)

        self._stored.ready[relation_name] = True

        if not (
            self._stored.ready.get("inbound-amqp")
            and self._stored.ready.get("outbound-amqp")
        ):
            self.unit.status = MaintenanceStatus(
                "Waiting for inbound and outbound AMQP details..."
            )
            return

        update_service_conf(
            {
                "broker": {
                    "host": hostname,
                    "password": password,
                }
            }
        )

        self.unit.status = ActiveStatus("Unit is ready")
        self._update_ready_status()

    def _update_haproxy(self) -> None:
        self._ensure_haproxy_installed()

        peer_ips = self.peer_ips

        if not peer_ips:
            logger.warning("Peer IPs not set, not updating HAProxy config.")
            return

        cert_attrs = self._get_certificate_request_attributes()
        if not cert_attrs:
            logger.warning("Unable to generate certificate request attributes.")
            return

        provider_certificate, private_key = (
            self.lb_certificates.get_assigned_certificate(
                certificate_request=cert_attrs
            )
        )

        if not provider_certificate or not private_key:
            self.unit.status = WaitingStatus(
                "Waiting for load balancer TLS certificate..."
            )
            logger.warning(
                "Certificate or private key is not yet available! "
                "Make sure this charm has been integrated with a "
                "provider of the `tls-certificates` charm interface."
            )
            self._update_ready_status()
            return

        self._stored.ready["load-balancer-certificates"] = True

        # Update root_url, if not provided.
        if not self.charm_config.root_url:
            url = f"https://{peer_ips.leader_ip}/"
            self._stored.default_root_url = url
            update_service_conf(
                {
                    "global": {"root-url": url},
                    "api": {"root-url": url},
                    "package-upload": {"root-url": url},
                }
            )

        try:
            haproxy.write_tls_cert(
                provider_certificate=provider_certificate, private_key=private_key
            )

        except haproxy.HAProxyError as e:
            logger.error("Failed to write TLS certificate for HAProxy: %s", str(e))
            self.unit.status = BlockedStatus(
                "Failed to write TLS certificate for HAProxy!"
            )
            return

        try:
            rendered = haproxy.render_config(
                all_ips=peer_ips.all_ips,
                leader_ip=peer_ips.leader_ip,
                worker_counts=self.charm_config.worker_counts,
                redirect_https=self.charm_config.redirect_https,
                enable_hostagent_messenger=self.charm_config.enable_hostagent_messenger,
                enable_ubuntu_installer_attach=self._stored.enable_ubuntu_installer_attach,
                max_connections=self.charm_config.max_global_haproxy_connections,
            )

        except haproxy.HAProxyError as e:
            logger.error("Failed to write HAProxy config: %s", str(e))
            return

        try:
            haproxy.validate_config()
        except haproxy.HAProxyError as e:
            logger.error("Failed to validate HAProxy config: %s", str(e))
            return

        try:
            haproxy.reload()
        except haproxy.HAProxyError as e:
            logger.error("Failed to reload HAProxy: %s", str(e))
            return

        self._stored.haproxy_config = rendered

        self._update_ready_status()

    def _on_get_certificates_action(self, event: ActionEvent) -> None:
        cert_attrs = self._get_certificate_request_attributes()
        if not cert_attrs:
            event.fail("TLS certificate not available")
            return

        provider_certificate, _ = self.lb_certificates.get_assigned_certificate(
            certificate_request=cert_attrs
        )

        if not provider_certificate:
            event.fail("No assigned TLS certificate found for this unit")
            return

        event.set_results(
            {
                "certificate": str(provider_certificate.certificate),
                "ca": str(provider_certificate.ca),
                "chain": "\n\n".join(
                    [str(cert) for cert in provider_certificate.chain]
                ),
            }
        )

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

        root_url = self.charm_config.root_url
        if not root_url:
            root_url = self._stored.default_root_url

        if not root_url:
            root_url = "https://" + str(
                self.model.get_binding(event.relation).network.bind_address
            )

        site_name = self.charm_config.site_name
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
        """
        Applies changes on non-leader units after a new leader is elected
        Deprecated call from Juju 3.x
        It is better to handler non-leader specific configuration by using
        the peer relation replicas_relation_changed contents
        """

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
            # Enable leader services on this unit.
            paused_services = (s for s in LEADER_SERVICES if not service_running(s))
            for service in paused_services:
                try:
                    service_resume(service)
                except SystemdError as e:
                    logger.warn(str(e))
        else:
            # Disable leader services on this unit. Requests will be directed to the
            # leader anyways.
            for service in LEADER_SERVICES:
                try:
                    service_pause(service)
                except SystemdError as e:
                    logger.warn(str(e))

        self._update_haproxy()
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

        if not self.unit.is_leader():
            if leader_ip_value:
                update_service_conf(
                    {
                        "package-search": {
                            "host": leader_ip_value,
                        },
                    }
                )

        self._leader_changed()

        secret_token = self._get_secret_token()
        should_update = False
        if (secret_token) and (secret_token != self._stored.secret_token):
            self._write_secret_token(secret_token)
            self._stored.secret_token = secret_token
            should_update = True

        cookie_encryption_key = self._get_cookie_encryption_key()
        if (
            cookie_encryption_key
            and cookie_encryption_key != self._stored.cookie_encryption_key
        ):
            self._write_cookie_encryption_key(cookie_encryption_key)
            self._stored.cookie_encryption_key = cookie_encryption_key
            should_update = True

        if should_update:
            self._update_ready_status(restart_services=True)

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
        if not self.charm_config.oidc_issuer:  # not doing OIDC
            return

        self.unit.status = MaintenanceStatus("Configuring OIDC")

        updates = {
            "landscape": {
                "oidc-issuer": self.charm_config.oidc_issuer,
                "oidc-client-id": self.charm_config.oidc_client_id,
                "oidc-client-secret": self.charm_config.oidc_client_secret,
            },
        }
        if self.charm_config.oidc_logout_url:
            updates["landscape"]["oidc-logout-url"] = self.charm_config.oidc_logout_url

        update_service_conf(updates)

        self.unit.status = WaitingStatus("Waiting on relations")

    def _configure_openid(self) -> None:
        if not self.charm_config.openid_provider_url:  # not doing OpenID
            return

        self.unit.status = MaintenanceStatus("Configuring OpenID")
        update_service_conf(
            {
                "landscape": {
                    "openid-provider-url": self.charm_config.openid_provider_url,
                    "openid-logout-url": self.charm_config.openid_logout_url,
                },
            }
        )
        self.unit.status = WaitingStatus("Waiting on relations")

    def _bootstrap_account(self):
        """If admin account details are provided, create admin"""
        if not self.unit.is_leader():
            return
        if self._stored.account_bootstrapped:  # Admin already created
            return
        karg = {}  # Keyword args for command line
        karg["admin_email"] = self.charm_config.admin_email
        karg["admin_name"] = self.charm_config.admin_name
        karg["admin_password"] = self.charm_config.admin_password
        required_args = karg.values()
        if not any(required_args):  # Return since no args are specified
            return
        if not all(required_args):  # Some required args are missing
            logger.error(
                "Admin email, name, and password required for bootstrap account"
            )
            return
        karg["root_url"] = self.charm_config.root_url
        if not karg["root_url"]:
            default_root_url = self._stored.default_root_url
            if default_root_url:
                karg["root_url"] = default_root_url
            else:
                logger.error("Bootstrap account waiting on default root url..")
                return
        karg["registration_key"] = self.charm_config.registration_key
        karg["system_email"] = self.charm_config.system_email

        # Collect command line arguments
        args = [BOOTSTRAP_ACCOUNT_SCRIPT]
        for key, value in karg.items():
            if not value:
                continue
            args.append("--" + key)
            args.append(value)

        secret_args = ["admin_password", "registration_key"]
        logged_args = get_args_with_secrets_removed(args, secret_args)
        logger.info(logged_args)

        try:
            result = subprocess.run(
                args, capture_output=True, text=True, env=get_modified_env_vars()
            )
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

    def _set_autoregistration(self) -> None:
        """Turns autoregistration on or off.

        Only the leader does this to prevent unnecessary DB writes.
        We can only do this after the initial account is bootstrapped.
        """
        on = "on" if self.charm_config.autoregistration else "off"

        if not self.unit.is_leader():
            return

        if not self._stored.account_bootstrapped:
            logger.error("Cannot modify autoregistration because no account exists.")
            return

        logger.info("Setting autoregistration...")
        result = subprocess.run(
            ["python3", AUTOREGISTRATION_SCRIPT, on],
            capture_output=True,
            text=True,
            env=get_modified_env_vars(),
        )

        logger.info(result.stdout)

        if result.returncode:
            logger.error(result.stderr)

    def _pause(self, event: ActionEvent) -> None:
        self.unit.status = MaintenanceStatus("Stopping services")
        event.log("Stopping services")

        try:
            check_call([LSCTL, "stop"], env=get_modified_env_vars())
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

        try:
            start_result = subprocess.run(
                [LSCTL, "start"],
                capture_output=True,
                text=True,
                env=get_modified_env_vars(),
            )
            check_call([LSCTL, "status"], env=get_modified_env_vars())
        except CalledProcessError as e:
            logger.error("Starting services failed with return code %d", e.returncode)
            logger.error("Failed to start services: %s", start_result.stdout)
            self.unit.status = MaintenanceStatus("Stopping services")
            subprocess.run([LSCTL, "stop"], env=get_modified_env_vars())
            self.unit.status = BlockedStatus("Failed to start services")
            event.fail(f"Failed to start services: {start_result.stdout}")
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
                if package == LANDSCAPE_SERVER:
                    check_call(["apt-mark", "unhold", LANDSCAPE_SERVER])
                pkg = apt.DebianPackage.from_apt_cache(package)
                pkg.ensure(state=apt.PackageState.Latest)
                installed = apt.DebianPackage.from_installed_package(package)
                event.log(f"Upgraded to {installed.version}...")
                if package == LANDSCAPE_SERVER:
                    check_call(["apt-mark", "hold", LANDSCAPE_SERVER])
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
            subprocess.run(
                [SCHEMA_SCRIPT], check=True, text=True, env=get_modified_env_vars()
            )
        except CalledProcessError as e:
            logger.error("Schema migration failed with error code %s", e.returncode)
            event.fail(f"Schema migration failed with error code {e.returncode}")
            self.unit.status = BlockedStatus("Failed schema migration")
        else:
            self.unit.status = prev_status

    def _hash_id_databases(self, event: ActionEvent) -> None:
        prev_status = self.unit.status
        self.unit.status = MaintenanceStatus("Hashing ID databases...")
        event.log("Running hash_id_databases")

        try:
            subprocess.run(
                ["sudo", "-u", "landscape", HASH_ID_DATABASES],
                check=True,
                text=True,
                env=get_modified_env_vars(),
            )
        except CalledProcessError as e:
            logger.error("Hashing ID databases failed with error code %s", e.returncode)
            event.fail(f"Hashing ID databases failed with error code {e.returncode}")
        finally:
            self.unit.status = prev_status

    def _migrate_service_conf(self, event: ActionEvent) -> None:
        migrate_service_conf()

    def _configure_ubuntu_installer_attach(self, enable: bool) -> None:
        """
        Install/uninstall the Ubuntu installer attach service. Do nothing if the
        configuration has not changed.
        """
        currently_enabled = self._stored.enable_ubuntu_installer_attach
        if not currently_enabled and enable:
            self.unit.status = MaintenanceStatus(
                "Installing `landscape-ubuntu-installer-attach`"
            )
            apt.add_package(LANDSCAPE_UBUNTU_INSTALLER_ATTACH, update_cache=True)
            self._stored.enable_ubuntu_installer_attach = True
        elif currently_enabled and not enable:
            self.unit.status = MaintenanceStatus(
                "Removing `landscape-ubuntu-installer-attach`"
            )
            apt.remove_package(LANDSCAPE_UBUNTU_INSTALLER_ATTACH)
            self._stored.enable_ubuntu_installer_attach = False


if __name__ == "__main__":  # pragma: no cover
    main(LandscapeServerCharm)
