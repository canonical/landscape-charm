import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template

from lib.hook import Hook
from lib.paths import default_paths
from lib.relations.postgresql import PostgreSQLRequirer
from lib.relations.rabbitmq import RabbitMQRequirer, RabbitMQProvider
from lib.relations.haproxy import HAProxyProvider, HAProxyRequirer
from lib.relations.landscape import (
    LandscapeLeaderContext, LandscapeRequirer, LandscapeProvider)
from lib.relations.config import ConfigRequirer
from lib.relations.hosted import HostedRequirer
from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.callbacks.filesystem import (
    EnsureConfigDir, WriteCustomSSLCertificate, WriteLicenseFile)
from lib.callbacks.apt import SetAPTSources


SERVICE_COUNTS = {
    "appserver": 2,
    "message-server": 2,
    "pingserver": 2,
}


class ServicesHook(Hook):
    """Execute service configuration logic.

    This hook uses the charm-helpers service framework to determine if we got
    all relation data we need in order to configure this Landscape unit, and
    proceed with the configuration if ready.
    """
    def __init__(self, hookenv=hookenv, host=host,
                 subprocess=subprocess, paths=default_paths, fetch=fetch):
        super(ServicesHook, self).__init__(hookenv=hookenv)
        self._hookenv = hookenv
        self._host = host
        self._paths = paths
        self._subprocess = subprocess
        self._fetch = fetch

    def _run(self):
        leader_context = None
        is_leader = self._hookenv.is_leader()
        if is_leader:
            leader_context = LandscapeLeaderContext(
                host=self._host, hookenv=self._hookenv)

        manager = ServiceManager(services=[{
            "service": "landscape",
            "ports": [],
            "provided_data": [
                LandscapeProvider(leader_context),
                HAProxyProvider(SERVICE_COUNTS, paths=self._paths),
                RabbitMQProvider(),
            ],
            # Required data is available to the render_template calls below.
            "required_data": [
                LandscapeRequirer(leader_context),
                ConfigRequirer(self._hookenv),
                PostgreSQLRequirer(),
                RabbitMQRequirer(),
                HAProxyRequirer(),
                HostedRequirer(),
                {"is_leader": is_leader,
                 "service_counts": SERVICE_COUNTS},
            ],
            "data_ready": [
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="service.conf", target=self._paths.service_conf()),
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="landscape-server",
                    target=self._paths.default_file()),
                SetAPTSources(
                    hookenv=self._hookenv, fetch=self._fetch,
                    subprocess=self._subprocess),
                EnsureConfigDir(paths=self._paths),
                WriteCustomSSLCertificate(paths=self._paths),
                SchemaBootstrap(subprocess=self._subprocess),
                WriteLicenseFile(host=self._host, paths=self._paths),
            ],
            "start": LSCtl(subprocess=self._subprocess, hookenv=self._hookenv),
        }])

        manager.manage()
