"""
Configuration for the Landscape charm.
"""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, root_validator
import yaml

# NOTE: the charm currently uses Pydantic 1.10


class LandscapeCharmConfiguration(BaseModel):
    """
    `landscape-server` charm configuration.
    """

    landscape_ppa: str
    landscape_ppa_key: str
    worker_counts: int
    license_file: str | None = None
    openid_provider_url: str | None = None
    openid_logout_url: str | None = None
    oidc_issuer: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None
    oidc_logout_url: str | None = None
    root_url: str | None = None
    system_email: str | None = None
    admin_email: str | None = None
    admin_name: str | None = None
    admin_password: str | None = None
    registration_key: str | None = None
    smtp_relay_host: str
    ssl_cert: str
    ssl_key: str
    http_proxy: str | None = None
    https_proxy: str | None = None
    no_proxy: str | None = None
    site_name: str
    nagios_context: str | None = None
    nagios_servicegroups: str | None = None
    db_host: str | None = None
    db_landscape_password: str | None = None
    db_port: str | None = None
    db_schema_user: str | None = None
    db_schema_password: str | None = None
    deployment_mode: str
    additional_service_config: str | None = None
    secret_token: str | None = None
    cookie_encryption_key: str | None = None
    min_install: bool
    prometheus_scrape_interval: str
    enable_ubuntu_installer_attach: bool
    autoregistration: bool

    @root_validator(skip_on_failure=True)
    def openid_oidc_exclusive(cls, values):
        OPENID_CONFIGS = (
            "openid_provider_url",
            "openid_logout_url",
        )
        OIDC_CONFIGS = (
            "oidc_issuer",
            "oidc_client_id",
            "oidc_client_secret",
            "oidc_logout_url",
        )

        openid = {v: values.get(v) for v in OPENID_CONFIGS}
        oidc = {v: values.get(v) for v in OIDC_CONFIGS}

        if any(openid.values()) and any(oidc.values()):
            raise ValueError(
                "OpenID and OIDC configurations are mutually exclusive. "
                f"Received OpenID configuration: {openid} and "
                f"OIDC configuration: {oidc}."
            )
        return values

    @root_validator(skip_on_failure=True)
    def openid_minimum_fields(cls, values):
        """
        If using either `openid_provider_url` or `openid_logout_url`, must provide both.
        """
        required_configs = ("openid_provider_url", "openid_logout_url")
        fields = {v: values.get(v) for v in required_configs}

        if any(fields.values()) and not all(fields.values()):
            raise ValueError(
                f"When using OpenID, must provide all of {required_configs}. "
                f"Got {fields}."
            )
        return values

    @root_validator(skip_on_failure=True)
    def oidc_minimum_fields(cls, values):
        """
        If providing any of `oidc_issuer`, `oidc_client_id`, or `oidc_client_secret`,
        must provide all three.
        """
        required_configs = ("oidc_issuer", "oidc_client_id", "oidc_client_secret")
        fields = {v: values.get(v) for v in required_configs}

        if any(fields.values()) and not all(fields.values()):
            raise ValueError(
                f"When using OIDC, must provide all of {required_configs}. "
                f"Got {fields}."
            )
        return values


def get_config_defaults() -> dict[str, Any]:
    """
    Get the `config.yaml`-defined configuration defaults for the charm.
    """
    config_file = Path(__file__).parent.parent / "config.yaml"
    assert config_file.exists(), f"Could not find config.yaml at {config_file}"

    with open(config_file) as f:
        raw = yaml.safe_load(f)

    configs = raw["options"]
    return {key: configs[key]["default"] for key in configs}


DEFAULT_CONFIGURATION = LandscapeCharmConfiguration.validate(get_config_defaults())
"""
A `LandscapeCharmConfiguration` populated with the defaults, for use as a fallback
when the charm is deployed with invalid configuration.
"""
