import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ManagerCallback

from lib.debconf import DebConf

# Schema of debconf options for postfix
POSTFIX_DEBCONF_SCHEMA = {
    "relayhost": "string",
    "main_mailer_type": "select"
}


class ConfigureSMTP(ManagerCallback):
    """Configure SMTP services according to the given configuration."""

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        self._hookenv = hookenv
        self._subprocess = subprocess

    def __call__(self, manager, service_name, event_name):
        config = self._hookenv.config()
        if manager.was_ready(service_name):
            if not config.changed("smtp-relay-host"):
                # Nothing to do
                return

        relay_host = config["smtp-relay-host"]
        if relay_host == "":
            mailer_type = "Internet Site"
        else:
            mailer_type = "Internet with smarthost"

        debconf = DebConf(
            "postfix", POSTFIX_DEBCONF_SCHEMA, subprocess=self._subprocess)
        debconf.set({"relayhost": relay_host, "main_mailer_type": mailer_type})
        debconf.reconfigure()
