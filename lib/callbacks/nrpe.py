# import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ManagerCallback
from charmhelpers.contrib.charmsupport import nrpe


# services running on all nodes
DEFAULT_SERVICES = ['landscape-api', 'landscape-appserver',
                    'landscape-async-frontend', 'landscape-job-handler',
                    'landscape-msgserver', 'landscape-pingserver']

# services running only on the leader
LEADER_SERVICES = ['landscape-package-search', 'landscape-package-upload']


class ConfigureNRPE(ManagerCallback):
    """Configure service checks if nrpe-external-master relation exists"""

    def __init__(self, hookenv=hookenv, nrpe_config=None):
        self._hookenv = hookenv
        self._unit = self._hookenv.local_unit()
        if nrpe_config:
            self._nrpe_config = nrpe_config
        else:
            self._nrpe_config = nrpe.NRPE()

    def __call__(self, manager, service_name, event_name):
        self._hookenv.log('Configure NRPE checks')
        if self._hookenv.relations_of_type('nrpe-external-master'):
            if self._hookenv.is_leader():
                self._add_checks(DEFAULT_SERVICES + LEADER_SERVICES)
            else:
                self._add_checks(DEFAULT_SERVICES)
                self._remove_checks(LEADER_SERVICES)
        else:
            self._remove_checks(DEFAULT_SERVICES + LEADER_SERVICES)
        self._nrpe_config.write()

    def _add_checks(self, services):
        """ add a service check """
        for service in services:
            hookenv.log('add nrpe check: %s' % service, hookenv.DEBUG)
            self._nrpe_config.add_check(
                    shortname='%s' % service,
                    description='process check {%s}' % self._unit,
                    check_cmd='check_systemd.py %s' % service)

    def _remove_checks(self, services):
        """ add a service check """
        for service in services:
            hookenv.log('remove nrpe check: %s' % service, hookenv.DEBUG)
            self._nrpe_config.remove_check(shortname=service)
