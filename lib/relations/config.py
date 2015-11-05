import psutil

from charmhelpers.core import hookenv
from lib.error import CharmError
from lib.utils import is_valid_url


class RootUrlNotValidError(CharmError):
    """Charm root-url is not a valid URL."""

    def __init__(self):
        message = (
            "The 'root-url' configuration value is not a valid URL. "
            "Please make sure it is of the form 'http[s]://<hostname>/'")
        super(RootUrlNotValidError, self).__init__(message)


class OpenIDConfigurationError(CharmError):
    """
    OpenID configuration is invalid.

    Both provider and logout URL must be set.
    """

    def __init__(self):
        message = (
            "To set up OpenID authentication, both 'openid-provider-url' "
            "and 'openid-logout-url' must be provided.")
        super(OpenIDConfigurationError, self).__init__(message)


class ConfigRequirer(dict):
    """Dependency manager for the service configuration.

    Take care of validating and exposing configuration values for use
    in service manager callbacks."""

    def __init__(self, hookenv=hookenv, psutil=psutil):
        self._psutil = psutil
        config = hookenv.config()
        self._validate(config)
        self.update({"config": config})

    def _calculate_service_counts(self, worker_count=None):
        """Return dict keyed by service names with desired number of processes.

        Scales by CPU count and RAM size.
        """
        if worker_count is None:
            cpu_cores = self._psutil.NUM_CPUS
            memory_in_gb = self._psutil.virtual_memory().total / (1024 ** 3)
            # For each extra CPU core and each extra 1GB of RAM (after 1GB),
            # we add another process.
            worker_count = 1 + cpu_cores + memory_in_gb - 2

        # Landscape startup scripts can only accept values between 1 and 9.
        worker_count = max(1, min(worker_count, 9))
        return {
            "appserver": worker_count,
            "message-server": worker_count,
            "pingserver": worker_count,
        }

    def _validate(self, config):
        root_url = config.get("root-url")
        if root_url and not is_valid_url(root_url):
            raise RootUrlNotValidError()

        # When OpenID authentication is requested, both 'openid_provider_url'
        # and 'openid_logout_url' must be defined in the configuration.
        openid_provider_url = config.get("openid-provider-url")
        openid_logout_url = config.get("openid-logout-url")
        if ((openid_provider_url and not openid_logout_url) or
                (not openid_provider_url and openid_logout_url)):
            raise OpenIDConfigurationError()

        worker_count = config.get("service-count", None)
        config["service-count"] = self._calculate_service_counts(worker_count)
