from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template
from charmhelpers.contrib.hahelpers import cluster

from lib.hook import Hook
from lib.relations.postgresql import PostgreSQLRequirer
from lib.relations.landscape import LandscapeRelation

SERVICE_CONF = "/etc/landscape/service.conf"


class ServicesHook(Hook):
    """Execute service configuration logic.

    This hook uses the charm-helpers service framework to determine if we got
    all relation data we need in order to configure this Landscape unit, and
    proceed with the configuration if ready.
    """
    def __init__(self, hookenv=hookenv, cluster=cluster, host=host):
        super(ServicesHook, self).__init__(hookenv=hookenv)
        self._cluster = cluster
        self._host = host

    def _run(self):
        landscape = LandscapeRelation(cluster=self._cluster, host=self._host)

        manager = ServiceManager([{
            "service": "landscape",
            "ports": [],
            "provided_data": [landscape],
            "required_data": [landscape, PostgreSQLRequirer()],
            "data_ready": [
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="service.conf", target=SERVICE_CONF),
            ],
        }])
        manager.manage()
