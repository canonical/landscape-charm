import psutil
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

    def _calculate_service_counts(self, hookenv=None, psutil=None):
        """Return dict keyed by service names with desired number of processes.

        Scales by CPU count and RAM size.
        """
        if hookenv is None:
            hookenv = self._hookenv
        if psutil is None:
            psutil = self._psutil
        service_count = hookenv.config().get("service-count", None)
        if service_count is None:
            cpu_cores = psutil.NUM_CPUS
            memory_in_gb = psutil.phymem_usage().total / (1024 ** 3)
            # For each extra CPU core and each extra 1GB of RAM (after 1GB),
            # we add another process.
            number_of_processes = 1 + cpu_cores + memory_in_gb - 2
            # Landscape startup scripts can only accept values between 1 and 9.
            service_count = max(1, min(number_of_processes, 9))
        return {
            "appserver": service_count,
            "message-server": service_count,
            "pingserver": service_count,
        }

    def _run(self):

        # XXX We need to manually kick the leader provider because atm the
        #     services framework only works with relation providers.
        leader_provider = LeaderProvider(
            hookenv=self._hookenv, host=self._host)
        leader_provider.provide_data()
        service_counts = self._calculate_service_counts()

        manager = ServiceManager(services=[{
            "service": "landscape",
            "ports": [],
            "provided_data": [
                HAProxyProvider(service_counts, paths=self._paths),
                RabbitMQProvider(),
            ],
            # Required data is available to the render_template calls below.
            "required_data": [
                LeaderRequirer(hookenv=self._hookenv),
                ConfigRequirer(hookenv=self._hookenv),
                PostgreSQLRequirer(),
                RabbitMQRequirer(),
                HAProxyRequirer(),
                HostedRequirer(),
                {"is_leader": self._hookenv.is_leader(),
                 "per_service_counts": service_counts},
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
                ConfigureSMTP(
                    hookenv=self._hookenv, subprocess=self._subprocess),
            ],
            "start": LSCtl(subprocess=self._subprocess, hookenv=self._hookenv),
        }])
        manager.manage()
