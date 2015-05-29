import os
import glob
import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv

from lib.hook import Hook, HookError
from lib.apt import Apt

# Pattern for pre-install hooks
CHARM_PRE_INSTALL_PATTERN = "exec.d/*/charm-pre-install"


class InstallHook(Hook):
    """Execute install hook logic."""

    def __init__(self, hookenv=hookenv, fetch=fetch, subprocess=subprocess):
        super(InstallHook, self).__init__(hookenv=hookenv)
        self._fetch = fetch
        self._subprocess = subprocess

    def _run(self):
        # Run pre-install hooks.
        self._hookenv.log("Invoking charm-pre-install hooks")
        charm_dir = self._hookenv.charm_dir()
        hooks = glob.glob(os.path.join(charm_dir, CHARM_PRE_INSTALL_PATTERN))
        for hook in hooks:
            if os.access(hook, os.X_OK):
                try:
                    self._subprocess.check_call(hook, shell=True)
                except subprocess.CalledProcessError as error:
                    raise HookError(str(error))

        # Set APT sources and install Landscape packages
        apt = Apt(
            hookenv=self._hookenv, fetch=self._fetch,
            subprocess=self._subprocess)
        apt.set_sources()
        apt.install_packages()
