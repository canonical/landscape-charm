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


class HoldPackages(ManagerCallback):
    """Marks landscape packages for hold.

    The exact list of packages depends on the deployment type, as passed by
    the HostedRequirer (depends on the state of the hosted relation)."""

    def __init__(self, subprocess=subprocess):
        # We only care about subprocess here since our hold packages method
        # on Apt needs nothing else.
        self._subprocess = subprocess

    def __call__(self, manager, service_name, event_name):
        apt = Apt(subprocess=self._subprocess)
        apt.hold_packages()
