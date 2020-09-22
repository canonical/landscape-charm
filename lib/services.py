import psutil
import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv
from charmhelpers.core import host
from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template

from lib.hook import Hook
from lib.paths import default_paths
from lib.relations.postgresql import PostgreSQLRequirer, PostgreSQLProvider
from lib.relations.rabbitmq import RabbitMQRequirer, RabbitMQProvider
from lib.relations.haproxy import HAProxyProvider, HAProxyRequirer
from lib.relations.leader import LeaderProvider, LeaderRequirer
from lib.relations.config import ConfigRequirer
from lib.relations.hosted import HostedRequirer
from lib.callbacks.scripts import SchemaBootstrap, LSCtl
from lib.callbacks.smtp import ConfigureSMTP
from lib.callbacks.filesystem import (
    EnsureConfigDir, WriteCustomSSLCertificate, WriteLicenseFile)
from lib.callbacks.apt import SetAPTSources


class ServicesHook(Hook):
    """Execute service configuration logic.

    This hook uses the charm-helpers service framework to determine if we got
    all relation data we need in order to configure this Landscape unit, and
    proceed with the configuration if ready.
    """
    def __init__(self, hookenv=hookenv, host=host,
                 subprocess=subprocess, paths=default_paths, fetch=fetch,
                 psutil=psutil):
        super(ServicesHook, self).__init__(hookenv=hookenv)
        self._hookenv = hookenv
        self._host = host
        self._paths = paths
        self._psutil = psutil
        self._subprocess = subprocess
        self._fetch = fetch

    def _run(self):

        # XXX We need to manually kick the leader provider because atm the
        #     services framework only works with relation providers.
        leader_provider = LeaderProvider(
            hookenv=self._hookenv, host=self._host)
        leader_provider.provide_data()

        config_requirer = ConfigRequirer(hookenv=self._hookenv)
        hosted_requirer = HostedRequirer(config_requirer)
        manager = ServiceManager(services=[{
            "service": "landscape",
            "ports": [],
            "provided_data": [
                HAProxyProvider(
                    config_requirer, hosted_requirer, paths=self._paths),
                RabbitMQProvider(),
                PostgreSQLProvider(database="landscape"),
            ],
            # Required data is available to the render_template calls below.
            "required_data": [
                LeaderRequirer(hookenv=self._hookenv),
                config_requirer,
                PostgreSQLRequirer(),
                RabbitMQRequirer(),
                HAProxyRequirer(),
                hosted_requirer,
                {"is_leader": self._hookenv.is_leader()},
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
                SchemaBootstrap(
                    subprocess=self._subprocess, hookenv=self._hookenv),
                WriteLicenseFile(host=self._host, paths=self._paths),
                ConfigureSMTP(
                    hookenv=self._hookenv, subprocess=self._subprocess),
            ],
            "start": LSCtl(subprocess=self._subprocess, hookenv=self._hookenv),
        }])
        try:
            manager.manage()
        except Exception as e:
            self._hookenv.log(str(e), level=hookenv.ERROR)
            raise
