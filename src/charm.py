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

from base64 import b64decode, b64encode, binascii
from dataclasses import asdict
from functools import cached_property
import os
import subprocess
from subprocess import CalledProcessError, check_call
from typing import List

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
    RelationDepartedEvent,
    RelationJoinedEvent,
    UpdateStatusEvent,
)
from ops.framework import StoredState
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    Relation,
    WaitingStatus,
)
from pydantic import ValidationError
import yaml

from config import LandscapeCharmConfiguration, RedirectHTTPS
from haproxy import (
    create_grpc_service,
    create_http_service,
    create_https_service,
    create_ubuntu_installer_attach_service,
    ERROR_FILES,
    get_haproxy_error_files,
    GRPC_SERVICE,
    HTTP_SERVICE,
    HTTPS_SERVICE,
    PORTS,
    SERVER_OPTIONS,
    UBUNTU_INSTALLER_ATTACH_SERVICE,
)
from helpers import get_modified_env_vars, logger, migrate_service_conf
from settings_files import (
    AMQP_USERNAME,
    configure_for_deployment_mode,
    DEFAULT_POSTGRES_PORT,
    generate_cookie_encryption_key,
    generate_secret_token,
    merge_service_conf,
    prepend_default_settings,
    update_db_conf,
    update_default_settings,
    update_service_conf,
    VHOSTS,
    write_license_file,
    write_ssl_cert,
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


def _get_ssl_cert(ssl_cert, ssl_key):
    """
    Create an SSL certificate from the `ssl_cert` and `ssl_key` configuration
    options.
    """
    if ssl_cert != "DEFAULT" and ssl_key == "":
        # We have a cert but no key, this is an error.
        raise SSLConfigurationError("`ssl_cert` is specified but `ssl_key` is missing")

    if ssl_cert != "DEFAULT":
        try:
            ssl_cert = b64decode(ssl_cert)
            ssl_key = b64decode(ssl_key)
            ssl_cert = b64encode(ssl_cert + b"\n" + ssl_key)
        except binascii.Error:
            raise SSLConfigurationError(
                "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded"
            )
    return ssl_cert


class InvalidRedirectHTTPS(Exception):
    """
    Raised when an invalid `redirect_https` configuration is provided.
    """


def _get_redirect_https(redirect_https: str) -> RedirectHTTPS:
    """
    Validate and return the `redirect_https` configuration parameter.

    Raises `InvalidRedirectHTTPS` if the provided value fails to validate.
    """
    try:
        return RedirectHTTPS(redirect_https)
    except ValueError:
        raise InvalidRedirectHTTPS(f"Invalid `https_redirect`: {redirect_https}")


class SSLConfigurationError(Exception):
    """
    Invalid SSL configuration.
    """


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
        self.framework.observe(
            self.on.migrate_service_conf_action, self._migrate_service_conf
        )
        self.framework.observe(
            self.on.enable_ubuntu_installer_attach_action,
            self._enable_ubuntu_installer_attach,
        )
        self.framework.observe(
            self.on.disable_ubuntu_installer_attach_action,
            self._disable_ubuntu_installer_attach,
        )

        # State
        self._stored.set_default(
            ready={
                "db": False,
                "inbound-amqp": False,
                "outbound-amqp": False,
                "haproxy": False,
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
        self._charm_config: LandscapeCharmConfiguration | None = None

    @property
    def charm_config(self) -> LandscapeCharmConfiguration:
        if self._charm_config is None:
            raise Exception(
                "Configuration is not initialized; need config-changed hook to run."
            )
        return self._charm_config

    def _generate_scrape_configs(self) -> list[dict]:
        """
        Return a scrape config for every metric-instrumented Landscape service.
        """
        return [
            {
                "scrape_interval": self.model.config.get("prometheus_scrape_interval"),
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
            self._charm_config = LandscapeCharmConfiguration.validate(self.model.config)
            self.unit.status = WaitingStatus("Configuration validated...")
        except ValidationError as e:
            logger.error(f"Invalid configuration: {e.errors()}")
            self.unit.status = BlockedStatus(
                "Invalid configuration. See `juju debug-log`."
            )
            return

        # Update additional configuration
        update_service_conf(
            {"global": {"deployment-mode": self.charm_config.deployment_mode}}
        )
        configure_for_deployment_mode(self.charm_config.deployment_mode)

        if self.charm_config.additional_service_config:
            merge_service_conf(self.charm_config.additional_service_config)

        if self.charm_config.ssl_cert != "DEFAULT":
            self.unit.status = MaintenanceStatus("Installing SSL certificate")
            write_ssl_cert(self.charm_config.ssl_cert)

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

        # Update HAProxy relations, if they exist.
        for relation in self.model.relations.get("website", []):
            self._update_haproxy_connection(relation)

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

        self._update_ready_status(restart_services=True)

    def _get_secret_token(self) -> str | None:
        """
        Get the `secret-token` config from either the juju config for this unit, or from
        app data in the replica relation.

        If set on neither, return `None`.
        """
        secret_token = self.model.config.get("secret_token")
        if not secret_token:
            peer_relation = self.model.get_relation("replicas")
            if peer_relation is not None:
                secret_token = peer_relation.data[self.app].get("secret-token", None)
            else:
                secret_token = None
        return secret_token

    def _get_cookie_encryption_key(self):
        cookie_encryption_key = self.model.config.get("cookie_encryption_key")
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
            # add-apt-repository doesn't use the proxy configuration from apt or juju
            # let's make sure to use the http(s) proxy settings from the charm or at
            # least any juju_proxy setting, add the classic http(s)_proxy to the env
            # that will be used only for add-apt-repository call
            add_apt_repository_env = os.environ.copy()
            for proxy_var in ["http_proxy", "https_proxy"]:
                juju_proxy_var = f"JUJU_CHARM_{proxy_var.upper()}"

                # if the charm has a proxy conf configured, override juju_http(s)
                # configuration
                if proxy_var in self.model.config:
                    add_apt_repository_env[proxy_var] = self.model.config[proxy_var]
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
            if "no_proxy" in self.model.config:
                add_apt_repository_env["no_proxy"] = self.model.config["no_proxy"]
                logger.info(
                    f"add-apt-repository no_proxy variable set to : "
                    f"{add_apt_repository_env['no_proxy']}"
                )

            check_call(
                ["add-apt-repository", "-y", landscape_ppa], env=add_apt_repository_env
            )

            if self.model.config["min_install"]:
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

        # Write the config-provided SSL certificate, if it exists.
        config_ssl_cert = self.model.config["ssl_cert"]

        if config_ssl_cert != "DEFAULT":
            self.unit.status = MaintenanceStatus("Installing SSL certificate")
            write_ssl_cert(config_ssl_cert)

        # Write the license file, if it exists.
        license_file = self.model.config.get("license_file")

        if license_file:
            self.unit.status = MaintenanceStatus("Writing Landscape license file")
            write_license_file(
                license_file, user_exists("landscape").pw_uid, self.root_gid
            )

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
            port = DEFAULT_POSTGRES_PORT  # Fall back to postgres default port

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

        if not self._update_wsl_distributions():
            return

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

    def _migrate_schema_bootstrap(self):
        """
        Migrates schema along with the bootstrap command which ensures that the
        databases and the landscape user exists, and that proxy settings are set.
        In addition, creates admin if configured.

        :returns: True on success.
        """
        call = [SCHEMA_SCRIPT, "--bootstrap"]

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
        try:
            ssl_cert = _get_ssl_cert(
                ssl_cert=self.model.config["ssl_cert"],
                ssl_key=self.model.config["ssl_key"],
            )
        except SSLConfigurationError as e:
            self.unit.status = BlockedStatus(str(e))
            return

        try:
            redirect_https = _get_redirect_https(
                str(self.model.config["redirect_https"])
            )
        except InvalidRedirectHTTPS as e:
            self.unit.status = BlockedStatus(str(e))
            return

        error_files = get_haproxy_error_files(ERROR_FILES)
        server_ip = relation.data[self.unit]["private-address"]
        unit_name = self.unit.name.replace("/", "-")
        worker_counts = int(self.model.config["worker_counts"])

        http_service = create_http_service(
            http_service=asdict(HTTP_SERVICE),
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=self.unit.is_leader(),
            error_files=error_files,
            service_ports=PORTS,
            server_options=SERVER_OPTIONS,
            redirect_https=redirect_https,
        )

        https_service = create_https_service(
            https_service=asdict(HTTPS_SERVICE),
            ssl_cert=ssl_cert,
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=self.unit.is_leader(),
            error_files=error_files,
            service_ports=PORTS,
            server_options=SERVER_OPTIONS,
        )

        grpc_service = create_grpc_service(
            grpc_service=asdict(GRPC_SERVICE),
            ssl_cert=ssl_cert,
            server_ip=server_ip,
            unit_name=unit_name,
            error_files=error_files,
            service_ports=PORTS,
            server_options=SERVER_OPTIONS,
        )

        services = [http_service, https_service, grpc_service]

        if self._stored.enable_ubuntu_installer_attach:
            services.append(
                create_ubuntu_installer_attach_service(
                    ubuntu_installer_attach_service=asdict(
                        UBUNTU_INSTALLER_ATTACH_SERVICE
                    ),
                    ssl_cert=ssl_cert,
                    server_ip=server_ip,
                    unit_name=unit_name,
                    error_files=error_files,
                    service_ports=PORTS,
                    server_options=SERVER_OPTIONS,
                )
            )

        relation.data[self.unit].update({"services": yaml.safe_dump(services)})
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

        # Sometimes the data has not been encoded properly in the HA charm
        if haproxy_ssl_cert.startswith("b'"):
            haproxy_ssl_cert = haproxy_ssl_cert.strip("b").strip("'")

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
            haproxy_relations = self.model.relations.get("website", [])
            for relation in haproxy_relations:
                self._update_haproxy_connection(relation)

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
        if (secret_token) and (secret_token != self._stored.secret_token):
            self._write_secret_token(secret_token)
            self._stored.secret_token = secret_token
            self._update_ready_status(restart_services=True)

        cookie_encryption_key = self._get_cookie_encryption_key()
        if (
            cookie_encryption_key
            and cookie_encryption_key != self._stored.cookie_encryption_key
        ):
            self._write_cookie_encryption_key(cookie_encryption_key)
            self._stored.cookie_encryption_key = cookie_encryption_key
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
        on = "on" if self.model.config["autoregistration"] else "off"

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

    def _enable_ubuntu_installer_attach(self, event: ActionEvent) -> None:
        """
        Install the Ubuntu installer attach and create the HAProxy frontend.
        """
        self._stored.enable_ubuntu_installer_attach = True
        apt.add_package(LANDSCAPE_UBUNTU_INSTALLER_ATTACH, update_cache=True)
        self._on_config_changed(None)

    def _disable_ubuntu_installer_attach(self, event: ActionEvent) -> None:
        """
        Uninstall the Ubuntu installer attach service and remove the HAProxy frontend.
        """
        self._stored.enable_ubuntu_installer_attach = False
        apt.remove_package(LANDSCAPE_UBUNTU_INSTALLER_ATTACH)
        self._on_config_changed(None)


if __name__ == "__main__":  # pragma: no cover
    main(LandscapeServerCharm)
