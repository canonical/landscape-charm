import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template
from charmhelpers.contrib.hahelpers import cluster

from lib.hook import Hook
from lib.relations.postgresql import PostgreSQLRequirer
from lib.relations.rabbitmq import RabbitMQRequirer, RabbitMQProvider
from lib.relations.haproxy import HAProxyProvider, OFFLINE_FOLDER
from lib.relations.landscape import (
    LandscapeLeaderContext, LandscapeRequirer, LandscapeProvider)
from lib.relations.hosted import HostedRequirer
from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.callbacks.filesystem import CONFIGS_DIR, EnsureConfigDir


SERVICE_CONF = "/etc/landscape/service.conf"
DEFAULT_FILE = "/etc/default/landscape-server"


class ServicesHook(Hook):
    """Execute service configuration logic.

    This hook uses the charm-helpers service framework to determine if we got
    all relation data we need in order to configure this Landscape unit, and
    proceed with the configuration if ready.
    """
    def __init__(self, hookenv=hookenv, cluster=cluster, host=host,
                 subprocess=subprocess, configs_dir=CONFIGS_DIR,
                 offline_dir=OFFLINE_FOLDER):
        super(ServicesHook, self).__init__(hookenv=hookenv)
        self._cluster = cluster
        self._host = host
        self._subprocess = subprocess
        self._configs_dir = configs_dir
        self._offline_dir = offline_dir

    def _run(self):
        leader_context = None
        is_leader = self._cluster.is_elected_leader(None)
        if is_leader:
            leader_context = LandscapeLeaderContext(host=self._host)

        manager = ServiceManager([{
            "service": "landscape",
            "ports": [],
            "provided_data": [
                LandscapeProvider(leader_context),
                HAProxyProvider(offline_dir=self._offline_dir),
                RabbitMQProvider(),
            ],
            "required_data": [
                LandscapeRequirer(leader_context),
                PostgreSQLRequirer(),
                RabbitMQRequirer(),
                HostedRequirer(),
                {"config": hookenv.config(),
                 "is_leader": is_leader},
            ],
            "data_ready": [
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="service.conf", target=SERVICE_CONF),
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="landscape-server", target=DEFAULT_FILE),
                EnsureConfigDir(configs_dir=self._configs_dir),
                SchemaBootstrap(subprocess=self._subprocess),
            ],
            "start": LSCtl(subprocess=self._subprocess),
        }])
        manager.manage()
