import os
import subprocess

from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ManagerCallback

from lib.paths import LSCTL, SCHEMA_SCRIPT
from lib.utils import get_required_data, update_persisted_data

# Configuration keys for which, in case of change, a restart is not needed.
NO_RESTART_CONFIG_KEYS = {
    "source", "key", "ssl-cert", "ssl-key", "smtp-relay-host"}

# Database relation keys for which, in case of change, a restart is not needed.
NO_RESTART_DB_RELATION_KEYS = {"allowed-units"}


class ScriptCallback(ManagerCallback):
    """Callback class for invoking Landscape scripts."""

    def __init__(self, subprocess=subprocess):
        self._subprocess = subprocess

    def _run(self, name, options=()):
        """Run the script with the given name and options."""
        command = [name]
        command += options
        self._subprocess.check_call(command)


class SchemaBootstrap(ScriptCallback):
    """Ensure that database users and schemas are setup.

    This will invoke the schema script with the --bootstrap flag, if it hasn't
    been called yet.
    """
    def __call__(self, manager, service_name, event_name):
        if not manager.was_ready(service_name):
            options = ["--bootstrap"]
            options.extend(self._get_proxy_options())
            self._run(SCHEMA_SCRIPT, options)

    def _get_proxy_options(self):
        """Return the HTTP proxy options to set.

        This method will check if the schema script has support for setting
        HTTP proxy options and if so return the appropriate ones by looking
        at the environment variables that Juju sets for us.
        """
        options = []

        help_output = self._subprocess.check_output([SCHEMA_SCRIPT, "-h"])
        if "--with-http-proxy" in help_output:
            # Forward any proxy configuration set in the environment
            for proxy_variable in ("http_proxy", "https_proxy", "no_proxy"):
                if proxy_variable in os.environ:
                    options.append("--with-%s=%s" % (
                        proxy_variable.replace("_", "-"),
                        os.environ[proxy_variable]))

        return options


class LSCtl(ScriptCallback):
    """Call the lsctl script to start or stop services."""

    def __init__(self, subprocess=subprocess, hookenv=hookenv):
        super(LSCtl, self).__init__(subprocess=subprocess)
        self._hookenv = hookenv

    def __call__(self, manager, service_name, event_name):
        current_status, current_status_message = self._hookenv.status_get()
        action_status_message = ""
        action = event_name
        if event_name == "start":
            # XXX the 'start' event in the services framework is called after
            #     config changes have been applied and its semantics actually
            #     maps to a 'restart' action.
            action = "restart"

        # Persist the new db connection details and fetch the old ones
        db_new = get_required_data(manager, service_name, "db")[0]
        db_old = update_persisted_data("db", db_new, hookenv=self._hookenv)

        # Persist the new leader settings and fetch the old ones
        leader_new = get_required_data(manager, service_name, "leader").copy()
        leader_new["is_leader"] = self._hookenv.is_leader()
        leader_old = update_persisted_data(
            "leader", leader_new, hookenv=self._hookenv)

        if action == "restart":
            # Check if we really need to kick a restart
            hook_name = self._hookenv.hook_name()
            if hook_name == "config-changed":
                if not self._need_restart_config_changed():
                    return
            elif hook_name == "db-relation-changed":
                if not self._need_restart_db_relation_changed(db_new, db_old):
                    return
            elif hook_name == "leader-settings-changed":
                if not self._need_restart_leader_settings_changed(
                        leader_new, leader_old):
                    return

            action_status_message = "Restarting services."
            if current_status == "unknown":
                # If the status is unknown, it means that the services
                # have not been started yet.
                action_status_message = "Starting services."
            if current_status == "maintenance":
                return

        self._hookenv.status_set("maintenance", action_status_message)
        self._run(LSCTL, (action,))
        self._hookenv.status_set("active", "")

    def _need_restart_config_changed(self):
        """Check whether we need to restart after a config change.

        In case we're reacting to config changes, we don't always want to
        restart the processes (for example if only the APT source or SSL
        certificate changed).
        """
        config = self._hookenv.config()
        changed = set()
        for key in config.keys():
            if config.changed(key):
                changed.add(key)
        if changed.issubset(NO_RESTART_CONFIG_KEYS):
            return False
        return True

    def _need_restart_db_relation_changed(self, db_new, db_old):
        """Check whether we need to restart after a db relation change.

        In case we're reacting to db relation changes, we don't want to
        restart the processes if connection details didn't change.
        """
        if db_old is None:
            return True
        new = db_new.copy()
        old = db_old.copy()
        for key in NO_RESTART_DB_RELATION_KEYS:
            new.pop(key)
            old.pop(key, None)
        return new != old

    def _need_restart_leader_settings_changed(self, leader_new, leader_old):
        """Check whether we need to restart after leader settings changed.

        Juju has no "leader-deposed" hook yet, however when a new leader gets
        elected the old leader unit that gets deposed will fire the
        "leader-settings-changed" hook, and we can then compare the new
        output of is-leader with the old one that we persisted, for determining
        if the leader unit is indeed being deposed.

        When the leader unit gets deposed we assume that it's because it is
        being removed, and so we avoid restarting services (which could
        error, for example if the postgresql charm has already fired
        its db-relation-departed hook and has removed our IP from the ACL).

        A better approach would be to not depend on juju leadership for
        deciding if a certain service should run or not, but rather use
        hacluster or make it possible to run all services on all units.

        See also the "guarantee that a long-lived process runs on just
        one unit at once" section here:

        https://jujucharms.com/docs/2.0/authors-charm-leadership

        There'a s bug to fix this in the long term: #1625500.
        """
        # We know that we have been the leader so far if it's not the first
        # hook invokation and in the previous invokation "hookenv.is_leader()"
        # was returning True.
        was_leader = leader_old is not None and leader_old["is_leader"]

        # If we were the leader, but we aren't anymore, don't restart.
        if was_leader and not leader_new["is_leader"]:
            return False

        return leader_new != leader_old
