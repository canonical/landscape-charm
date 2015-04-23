from charmhelpers.core import hookenv
from lib.hook import HookError
from lib.utils import is_valid_url


class ConfigRequirer(dict):
    """Dependency manager for the service configuration.

    Take care of validating and exposing configuration values for use
    in service manager callbacks."""

    def __init__(self, hookenv=hookenv):
        config = hookenv.config()
        self._validate(config)
        self.update({"config": config})

    def _validate(self, config):
        root_url = config.get("root-url")
        if root_url and not is_valid_url(root_url):
            raise HookError(
                "The 'root-url' configuration value is not a valid URL."
                " Please make sure it is of the form"
                " 'http[s]://<hostname>/'")
