# Copyright 2022 Canonical Ltd

"""
Functions for manipulating Landscape Server service settings in the
filesystem.
"""

from base64 import b64decode, binascii
from collections import defaultdict
from configparser import ConfigParser
from dataclasses import dataclass
import os
import secrets
from string import ascii_letters, digits
from urllib.error import URLError
from urllib.request import urlopen

CONFIGS_DIR = "/opt/canonical/landscape/configs"

DEFAULT_SETTINGS = "/etc/default/landscape-server"

LICENSE_FILE = "/etc/landscape/license.txt"
LICENSE_FILE_PROTOCOLS = (
    "file://",
    "http://",
    "https://",
)

SERVICE_CONF = "/etc/landscape/service.conf"
SSL_CERT_PATH = "/etc/ssl/certs/landscape_server_ca.crt"

DEFAULT_POSTGRES_PORT = "5432"

AMQP_USERNAME = "landscape"
VHOSTS = {
    "inbound-amqp": "landscape",
    "outbound-amqp": "landscape-hostagent",
}


class LicenseFileReadException(Exception):
    pass


class SSLCertReadException(Exception):
    pass


class ServiceConfMissing(Exception):
    pass


class SecretTokenMissing(Exception):
    pass


def configure_for_deployment_mode(mode: str) -> None:
    """
    Places files where Landscape expects to find them for different deployment
    modes.
    """
    if mode == "standalone":
        return

    sym_path = os.path.join(CONFIGS_DIR, mode)

    if os.path.exists(sym_path):
        return

    os.symlink(os.path.join(CONFIGS_DIR, "standalone"), sym_path)


def merge_service_conf(other: str) -> None:
    """
    Merges `other` into the Landscape Server configuration file,
    overwriting existing config.
    """
    config = ConfigParser()
    config.read(SERVICE_CONF)
    config.read_string(other)

    with open(SERVICE_CONF, "w") as config_fp:
        config.write(config_fp)


def prepend_default_settings(updates: dict) -> None:
    """
    Adds `updates` to the start of the Landscape Server default
    settings file.
    """
    with open(DEFAULT_SETTINGS, "r") as settings_fp:
        settings = settings_fp.read()

    with open(DEFAULT_SETTINGS, "w") as settings_fp:
        for k, v in updates.items():
            settings_fp.write(f'{k}="{v}"\n')

        settings_fp.write(settings)


def update_default_settings(updates: dict) -> None:
    """
    Updates the Landscape Server default settings file.

    This file is mainly used to determine which services should be
    running for this installation.
    """
    with open(DEFAULT_SETTINGS, "r") as settings_fp:
        new_lines = []

        for line in settings_fp:
            if "=" in line and line.split("=")[0] in updates:
                key = line.split("=")[0]
                new_line = f'{key}="{updates[key]}"\n'
            else:
                new_line = line

            new_lines.append(new_line)

    with open(DEFAULT_SETTINGS, "w") as settings_file:
        settings_file.write("".join(new_lines))


def update_service_conf(updates: dict) -> None:
    """
    Updates the Landscape Server configuration file.

    `updates` is a mapping of {section => {key => value}}, to be applied
        to the config file.
    """
    if not os.path.isfile(SERVICE_CONF):
        # Landscape server will not overwrite this file on install, so we
        # cannot get the default values if we create it here
        raise ServiceConfMissing("Landscape server install failed!")

    config = ConfigParser()
    config.read(SERVICE_CONF)

    for section, data in updates.items():
        for key, value in data.items():
            if not config.has_section(section):
                config.add_section(section)

            config[section][key] = value

    with open(SERVICE_CONF, "w") as config_fp:
        config.write(config_fp)


def generate_secret_token():
    alphanumerics = ascii_letters + digits
    return "".join(secrets.choice(alphanumerics) for _ in range(172))


def write_license_file(license_file: str, uid: int, gid: int) -> None:
    """
    Reads or decodes `license_file` to LICENSE_FILE and sets it up
    ownership for `uid` and `gid`.

    raises LicenseFileReadException if the location `license_file`
    cannot be read
    """

    if any((license_file.startswith(proto) for proto in LICENSE_FILE_PROTOCOLS)):
        try:
            license_file_data = urlopen(license_file).read()
        except URLError:
            raise LicenseFileReadException(
                f"Unable to read license file at {license_file}"
            )
    else:
        # Assume b64-encoded
        try:
            license_file_data = b64decode(license_file.encode())
        except binascii.Error:
            raise LicenseFileReadException("Unable to read b64-encoded license file")

    with open(LICENSE_FILE, "wb") as license_fp:
        license_fp.write(license_file_data)

    os.chmod(LICENSE_FILE, 0o640)
    os.chown(LICENSE_FILE, uid, gid)


def write_ssl_cert(ssl_cert: str) -> None:
    """Decodes and writes `ssl_cert` to `SSL_CERT_PATH`."""
    try:
        with open(SSL_CERT_PATH, "wb") as ssl_cert_fp:
            ssl_cert_fp.write(b64decode(ssl_cert.encode()))
    except binascii.Error:
        raise SSLCertReadException("Unable to decode b64-encoded SSL certificate")


def update_db_conf(
    host=None,
    password=None,
    schema_password=None,
    port=DEFAULT_POSTGRES_PORT,
    user=None,
):
    """Postgres specific settings override"""
    to_update = defaultdict(dict)
    if host:  # Note that host is required if port is changed
        to_update["stores"]["host"] = "{}:{}".format(host, port)
    if password:
        to_update["stores"]["password"] = password
        to_update["schema"]["store_password"] = password
    if schema_password:  # Overrides password
        to_update["schema"]["store_password"] = schema_password
    if user:
        to_update["schema"]["store_user"] = user
    if to_update:
        update_service_conf(to_update)


# The helpers below are essentially copied from the
# Landscape Server code. They are needed to migrate the service.conf
# file to migrate sections and options that are deprecated in Landscape
# Server 25.10.
# In Landscape Server 26.04, the deprecated portions of service.conf
# will no longer be supported, and the migration helpers below will
# no longer be needed.
@dataclass
class DeprecatedValue:
    new_key: str
    new_section: str | None = None


DEPRECATED_SERVICE_OPTIONS = {
    "base-port": DeprecatedValue(new_key="base_port"),
    "enable-metrics": DeprecatedValue(new_key="enable_metrics"),
    "gpg-home-path": DeprecatedValue(new_key="gpg_home_path"),
    "gpg-passphrase-path": DeprecatedValue(new_key="gpg_passphrase_path"),
    "mailer-path": DeprecatedValue(new_key="mailer_path"),
    "oops-key": DeprecatedValue(new_key="oops_key"),
    "soft-timeout": DeprecatedValue(new_key="soft_timeout"),
}


DEPRECATED_SECTIONS = {
    "async-frontend": "async_frontend",
    "fake-openid": "fake_openid",
    "global": "system",
    "job-handler": "job_handler",
    "hostagent-message-consumer": "hostagent_consumer",
    "hostagent-message-server": "hostagent_server",
    "landscape": "appserver",
    "load-shaper": "load_shaper",
    "message-server": "message_server",
    "package-search": "package_search",
    "package-upload": "package_upload",
    "ubuntu-installer-attach-message-server": "ubuntu_installer_attach",
}


DELETED_SECTIONS = {"pppa-proxy"}


DEPRECATED_OPTIONS = {
    "api": {
        "cookie-encryption-key": DeprecatedValue(new_key="cookie_encryption_key"),
        "cors-allow-all": DeprecatedValue(new_key="cors_allow_all"),
        "root-url": DeprecatedValue(new_key="root_url"),
        "snap-store-api-url": DeprecatedValue(new_key="snap_store_api_url"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "appserver": {
        "blob-storage-root": DeprecatedValue(new_key="blob_storage_root"),
        "display-consent-banner-at-each-login": DeprecatedValue(
            new_key="display_consent_banner_at_each_login"
        ),
        "enable-password-authentication": DeprecatedValue(
            new_key="enable_password_authentication", new_section="system"
        ),
        "enable-saas-metrics": DeprecatedValue(
            new_key="enable_saas_metrics", new_section="system"
        ),
        "enable-subdomain-accounts": DeprecatedValue(
            new_key="enable_subdomain_accounts", new_section="system"
        ),
        "enable-tag-script-execution": DeprecatedValue(
            new_key="enable_tag_script_execution", new_section="system"
        ),
        "juju-homes-path": DeprecatedValue(new_key="juju_homes_path"),
        "known-proxies": DeprecatedValue(new_key="juju_homes_path"),
        "openid-provider-url": DeprecatedValue(new_key="openid_provider_url"),
        "openid-logout-url": DeprecatedValue(new_key="openid_logout_url"),
        "oidc-client-id": DeprecatedValue(new_key="oidc_client_id"),
        "oidc-client-secret": DeprecatedValue(new_key="oidc_client_secret"),
        "oidc-issuer": DeprecatedValue(new_key="oidc_issuer"),
        "oidc-provider": DeprecatedValue(new_key="oidc_provider"),
        "oidc-redirect-uri": DeprecatedValue(new_key="oidc_redirect_uri"),
        "repository-path": DeprecatedValue(new_key="repository_path"),
        "reprepro-binary": DeprecatedValue(new_key="reprepro_binary"),
        "sanitize-delay": DeprecatedValue(new_key="sanitize_delay"),
        "secret-token": DeprecatedValue(new_key="secret_token"),
        "ubuntu-images-path": DeprecatedValue(new_key="ubuntu_images_path"),
        "ubuntu-one-redirect-url": DeprecatedValue(new_key="ubuntu_one_redirect_url"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "async_frontend": DEPRECATED_SERVICE_OPTIONS,
    "fake_openid": {
        "root-url": DeprecatedValue(new_key="root_url"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "features": {
        "enable-employee-management": DeprecatedValue(new_key="employee_management"),
        "enable-script-profiles": DeprecatedValue(new_key="script_profiles"),
        "enable-self-service-account-creation": DeprecatedValue(
            new_key="self_service_account_creation"
        ),
        "enable-self-service-payg": DeprecatedValue(new_key="self_service_payg"),
        "enable-support-provider-login": DeprecatedValue(
            new_key="support_provider_login"
        ),
        "enable-ubuntu-pro-licensing": DeprecatedValue(new_key="ubuntu_pro_licensing"),
        "enable-usg-profiles": DeprecatedValue(new_key="usg_profiles"),
        "enable-wsl-child-instance-profiles": DeprecatedValue(new_key="wsl_management"),
    },
    "hostagent_consumer": DEPRECATED_SERVICE_OPTIONS,
    "hostagent_server": DEPRECATED_SERVICE_OPTIONS,
    "job_handler": {
        "accumulator-reconnection-delay": DeprecatedValue(
            new_key="accumulator_reconnection_delay"
        ),
        "default-accumulator-delay": DeprecatedValue(
            new_key="default_accumulator_delay"
        ),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "load_shaper": {
        "critical-load": DeprecatedValue(new_key="critical_load"),
        "good-duration": DeprecatedValue(new_key="good_duration"),
        "good-load": DeprecatedValue(new_key="good_load"),
    },
    "maintenance": DEPRECATED_SERVICE_OPTIONS,
    "message_server": {
        "backoff-dirpath": DeprecatedValue(new_key="backoff_dirpath"),
        "check-interval": DeprecatedValue(new_key="check_interval"),
        "max-msg-size-bytes": DeprecatedValue(new_key="max_msg_size_bytes"),
        "message-snippet-bytes": DeprecatedValue(new_key="message_snippet_bytes"),
        "ping-interval": DeprecatedValue(new_key="ping_interval"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "oops": {
        "amqp-exchange": DeprecatedValue(new_key="amqp_exchange"),
        "amqp-key": DeprecatedValue(new_key="amqp_key"),
    },
    "package_search": {
        "account-threshold": DeprecatedValue(new_key="account_threshold"),
        "pid-path": DeprecatedValue(new_key="pid_path"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "package_upload": {
        "root-url": DeprecatedValue(new_key="service_path"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "pingserver": {
        "database-check-interval": DeprecatedValue(new_key="database_check_interval"),
        "database-write-interval": DeprecatedValue(new_key="database_write_interval"),
        "pingtracker-penalty-window-duration": DeprecatedValue(
            new_key="pingtracker_penalty_window_duration"
        ),
        "pingtracker-window-duration": DeprecatedValue(
            new_key="pingtracker_window_duration"
        ),
        "pingtracker-window-ping-limit": DeprecatedValue(
            new_key="pingtracker_window_ping_limit"
        ),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "schema": DEPRECATED_SERVICE_OPTIONS,
    "scripts": DEPRECATED_SERVICE_OPTIONS,
    "secrets": {
        "secrets-url": DeprecatedValue(new_key="vault_url"),
        "secrets-service-url": DeprecatedValue(new_key="service_url"),
    }
    | DEPRECATED_SERVICE_OPTIONS,
    "stores": {
        "account-1": DeprecatedValue(new_key="account_1"),
        "account-2": DeprecatedValue(new_key="account_2"),
        "resource-1": DeprecatedValue(new_key="resource_1"),
        "resource-2": DeprecatedValue(new_key="resource_2"),
        "session-autocommit": DeprecatedValue(new_key="session_autocommit"),
    },
    "system": {
        "audit-retention-period": DeprecatedValue(new_key="audit_retention_period"),
        "deployment-mode": DeprecatedValue(new_key="deployment_mode"),
        "max-service-memory": DeprecatedValue(new_key="max_service_memory"),
        "oops-path": DeprecatedValue(new_key="oops_path"),
        "pidfile-directory": DeprecatedValue(new_key="pidfile_directory"),
        "root-url": DeprecatedValue(new_key="root_url"),
        "syslog-address": DeprecatedValue(new_key="syslog_address"),
    },
    "ubuntu_installer_attach": DEPRECATED_SERVICE_OPTIONS,
}


def read_service_conf(service_conf=SERVICE_CONF) -> ConfigParser:
    config = ConfigParser()
    config.read(service_conf)
    return config


def migrate_service_conf(service_conf=SERVICE_CONF):
    config = read_service_conf(service_conf)
    new_config = defaultdict(dict)
    for section in config.sections():
        settings = config._sections[section]
        if section in DEPRECATED_SECTIONS:
            new_section = DEPRECATED_SECTIONS[section]
            new_config[new_section] |= settings
        elif section not in DELETED_SECTIONS:
            new_config[section] |= settings
    for new_section in DEPRECATED_SECTIONS.values():
        if new_section not in new_config:
            new_config[new_section] = {}
    for section, deprecations in DEPRECATED_OPTIONS.items():
        if section in new_config:
            for deprecated_option, new_option in deprecations.items():
                if deprecated_option in new_config[section]:
                    value = new_config[section].pop(deprecated_option)
                    if new_option.new_section is not None:
                        new_section = new_option.new_section
                    else:
                        new_section = section
                    new_config[new_section][new_option.new_key] = value
    updated_config = ConfigParser()
    updated_config.read_dict(new_config)
    with open(service_conf, "w") as config_fp:
        updated_config.write(config_fp)
