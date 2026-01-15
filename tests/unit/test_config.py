from pydantic import ValidationError
import pytest

from src.config import (
    DEFAULT_CONFIGURATION,
    get_config_defaults,
    LandscapeCharmConfiguration,
    RedirectHTTPS,
)


def test_defaults():
    """
    Get a default configuration.
    """

    config = DEFAULT_CONFIGURATION

    assert config.landscape_ppa == "ppa:landscape/self-hosted-beta"
    assert config.landscape_ppa_key == ""
    assert config.worker_counts == 2
    assert config.license_file is None

    assert config.openid_provider_url is None
    assert config.openid_logout_url is None
    assert config.oidc_issuer is None
    assert config.oidc_client_id is None
    assert config.oidc_logout_url is None

    assert config.root_url is None
    assert config.system_email is None
    assert config.admin_email is None
    assert config.admin_name is None
    assert config.admin_password is None
    assert config.registration_key is None

    assert config.smtp_relay_host == ""

    assert config.http_proxy is None
    assert config.https_proxy is None
    assert config.no_proxy is None

    assert config.site_name == "juju"

    assert config.nagios_context == "juju"
    assert config.nagios_servicegroups is None

    assert config.db_host is None
    assert config.db_landscape_password is None
    assert config.db_port is None
    assert config.db_schema_user is None
    assert config.db_schema_password is None

    assert config.deployment_mode == "standalone"
    assert config.additional_service_config is None
    assert config.secret_token is None
    assert config.cookie_encryption_key is None
    assert not config.min_install
    assert config.prometheus_scrape_interval == "1m"
    assert not config.autoregistration
    assert config.redirect_https == RedirectHTTPS.DEFAULT

    assert not config.enable_hostagent_messenger
    assert not config.enable_ubuntu_installer_attach
    assert config.max_global_haproxy_connections == 4096


@pytest.mark.parametrize(
    "openid_parameter",
    ["openid_provider_url", "openid_logout_url"],
)
def test_openid_oidc_exlusive_openid(openid_parameter):
    """
    If OIDC is configured, cannot configure OpenID.
    """
    defaults = get_config_defaults()
    defaults["oidc_issuer"] = "https://oidc-issuer.test"
    defaults[openid_parameter] = "https://some-url.test"
    with pytest.raises(ValidationError, match="mutually exclusive"):
        LandscapeCharmConfiguration(**defaults)


@pytest.mark.parametrize(
    "oidc_parameter",
    ["oidc_issuer", "oidc_client_id", "oidc_client_secret", "oidc_logout_url"],
)
def test_openid_oidc_exlusive_oidc(oidc_parameter):
    """
    If OpenID is configured, cannot configure OIDC.
    """
    defaults = get_config_defaults()
    defaults["openid_provider_url"] = "https://open-provider.test"
    defaults[oidc_parameter] = "https://some-url.test"
    with pytest.raises(ValidationError, match="mutually exclusive"):
        LandscapeCharmConfiguration(**defaults)


@pytest.mark.parametrize(
    "openid_provider_url,openid_logout_url,valid",
    [
        ("https://some-url.test", "https://some-url.test", True),
        (None, "https://some-url.test", False),
        ("https://some-url.test", None, False),
        (None, None, True),
    ],
)
def test_openid_minimum_fields(openid_provider_url, openid_logout_url, valid):
    """
    OpenID requires both `openid_provider_url` and `openid_logout_url` if either
    are provided.
    """
    defaults = get_config_defaults()
    defaults["openid_provider_url"] = openid_provider_url
    defaults["openid_logout_url"] = openid_logout_url

    if not valid:
        with pytest.raises(ValidationError):
            LandscapeCharmConfiguration(**defaults)
    else:
        LandscapeCharmConfiguration(**defaults)


@pytest.mark.parametrize(
    "oidc_issuer,oidc_client_id,oidc_client_secret,oidc_logout_url,valid",
    [
        ("https://login.test", "clientid", "clientsecret", "https://logout.test", True),
        (None, "clientid", "clientsecret", "https://logout.test", False),
        ("https://login.test", None, "clientsecret", "https://logout.test", False),
        ("https://login.test", "clientid", None, "https://logout.test", False),
        ("https://login.test", "clientid", "clientsecret", None, True),
        ("https://login.test", None, None, None, False),
        (None, None, None, None, True),
    ],
)
def test_oidc_minimum_fields(
    oidc_issuer, oidc_client_id, oidc_client_secret, oidc_logout_url, valid
):
    """
    OIDC requires all of `oidc_issuer`, `oidc_client_id`, `oidc_client_secret`. The
    `oidc_logout_url` is optional.
    """
    defaults = get_config_defaults()
    defaults["oidc_issuer"] = oidc_issuer
    defaults["oidc_client_id"] = oidc_client_id
    defaults["oidc_client_secret"] = oidc_client_secret
    defaults["oidc_logout_url"] = oidc_logout_url

    if not valid:
        with pytest.raises(ValidationError):
            LandscapeCharmConfiguration(**defaults)
    else:
        LandscapeCharmConfiguration(**defaults)
