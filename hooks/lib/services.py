from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template
from charmhelpers.contrib.hahelpers import cluster

from lib.hook import Hook
from lib.relations.postgresql import PostgreSQLRequirer
from lib.relations.landscape import (
    LandscapeLeaderContext, LandscapeRequirer, LandscapeProvider)

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
        leader_context = None

        provided_data = []
        if self._cluster.is_elected_leader(None):
            # If we are the leader unit, provide our leader context to the
            # other peer Landscape units using the landscape-ha relation.
            leader_context = LandscapeLeaderContext(host=self._host)
            provided_data.append(LandscapeProvider(leader_context))

        required_data = [
            LandscapeRequirer(leader_context),
            PostgreSQLRequirer(),
        ]

        manager = ServiceManager([{
            "service": "landscape",
            "ports": [],
            "provided_data": provided_data,
            "required_data": required_data,
            "data_ready": [
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="service.conf", target=SERVICE_CONF),
            ],
        }])
        manager.manage()
