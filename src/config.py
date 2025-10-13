"""
Configuration for the Landscape charm.
"""

from enum import Enum
from pydantic import BaseModel, root_validator


class RedirectHTTPS(str, Enum):
    """
    Keywords to specify which HTTP routes should be redirected to HTTPS.
    """

    ALL = "all"
    NONE = "none"
    DEFAULT = "default"


# NOTE: the charm currently uses Pydantic 1.10


class LandscapeCharmConfiguration(BaseModel):
    """
    `landscape-server` charm configuration.
    """

    landscape_ppa: str
    landscape_ppa_key: str
    worker_counts: int
    license_file: str | None
    openid_provider_url: str | None
    openid_logout_url: str | None
    oidc_issuer: str | None
    oidc_client_id: str | None
    oidc_client_secret: str | None
    oidc_logout_url: str | None = None
    root_url: str | None
    system_email: str | None
    admin_email: str | None
    admin_name: str | None
    admin_password: str | None
    registration_key: str | None
    smtp_relay_host: str
    ssl_cert: str
    ssl_key: str
    http_proxy: str | None
    https_proxy: str | None
    no_proxy: str | None
    site_name: str
    nagios_context: str | None
    nagios_servicegroups: str | None
    db_host: str | None
    db_landscape_password: str | None
    db_port: str | None
    db_schema_user: str | None
    db_schema_password: str | None
    deployment_mode: str
    additional_service_config: str | None
    secret_token: str | None
    cookie_encryption_key: str | None
    min_install: bool
    prometheus_scrape_interval: str
    autoregistration: bool
    redirect_https: RedirectHTTPS

    @root_validator(allow_reuse=True)
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

    @root_validator(allow_reuse=True)
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

    @root_validator(allow_reuse=True)
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
