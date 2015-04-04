import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template
from charmhelpers.contrib.hahelpers import cluster

from lib.hook import Hook
from lib.relations.postgresql import PostgreSQLRequirer
from lib.relations.rabbitmq import RabbitMQRequirer, RabbitMQProvider
from lib.relations.haproxy import HAProxyProvider
from lib.relations.landscape import (
    LandscapeLeaderContext, LandscapeRequirer, LandscapeProvider)
from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.assets import OFFLINE_FOLDER

SERVICE_CONF = "/etc/landscape/service.conf"
DEFAULT_FILE = "/etc/default/landscape-server"


class ServicesHook(Hook):
    """Execute service configuration logic.

    This hook uses the charm-helpers service framework to determine if we got
    all relation data we need in order to configure this Landscape unit, and
    proceed with the configuration if ready.
    """
    def __init__(self, hookenv=hookenv, cluster=cluster, host=host,
                 subprocess=subprocess, offline_folder=OFFLINE_FOLDER):
        super(ServicesHook, self).__init__(hookenv=hookenv)
        self._cluster = cluster
        self._host = host
        self._subprocess = subprocess
        self._offline_folder = offline_folder

    def _run(self):
        leader_context = None
        if self._cluster.is_elected_leader(None):
            leader_context = LandscapeLeaderContext(host=self._host)

        manager = ServiceManager([{
            "service": "landscape",
            "ports": [],
            "provided_data": [
                LandscapeProvider(leader_context),
                HAProxyProvider(offline_folder=self._offline_folder),
                RabbitMQProvider(),
            ],
            "required_data": [
                LandscapeRequirer(leader_context),
                PostgreSQLRequirer(),
                RabbitMQRequirer(),
            ],
            "data_ready": [
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="service.conf", target=SERVICE_CONF),
                render_template(
                    owner="root", group="root", perms=0o640,
                    source="landscape-server", target=DEFAULT_FILE),
                SchemaBootstrap(subprocess=self._subprocess),
            ],
            "start": LSCtl(subprocess=self._subprocess),
        }])
        manager.manage()
