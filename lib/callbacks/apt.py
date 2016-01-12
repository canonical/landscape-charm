import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ManagerCallback

from lib.apt import Apt


class SetAPTSources(ManagerCallback):
    """Set APT sources and refresh them if needed."""

    def __init__(self, hookenv=hookenv, fetch=fetch, subprocess=subprocess):
        self._hookenv = hookenv
        self._fetch = fetch
        self._subprocess = subprocess

    def __call__(self, manager, service_name, event_name):
        # Re-set APT sources, if they have changed.
        apt = Apt(
            hookenv=self._hookenv, fetch=self._fetch,
            subprocess=self._subprocess)
        apt.set_sources()
