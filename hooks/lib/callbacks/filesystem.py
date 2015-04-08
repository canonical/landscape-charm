# Filesystem-related callbacks

import os

from charmhelpers.core.services.base import ManagerCallback

CONFIGS_DIR = "/opt/canonical/landscape/configs"


class EnsureConfigDir(ManagerCallback):
    """Ensure that the config dir for the configured deployment mode exists.

    XXX This is a temporary workaround till we make the Landscape server
        code always look at the same location for configuration files.
    """
    def __init__(self, configs_dir=CONFIGS_DIR):
        self._configs_dir = configs_dir

    def __call__(self, manager, service_name, event_name):
        service = manager.get_service(service_name)

        # Lookup the deployment mode
        for data in service.get("required_data"):
            if "hosted" in data:
                deployment_mode = data["hosted"][0]["deployment-mode"]
                break

        # Create a symlink for the config directory
        config_link = os.path.join(self._configs_dir, deployment_mode)
        if not os.path.exists(config_link):
            standalone_dir = os.path.join(self._configs_dir, "standalone")
            os.symlink(standalone_dir, config_link)
