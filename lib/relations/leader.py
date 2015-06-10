from charmhelpers.core.services.helpers import RelationContext
from charmhelpers.core import host, hookenv


class LeaderProvider(object):
    """Provide leader data meant to be shared across all units."""

    def __init__(self, hookenv=hookenv, host=host):
        self._hookenv = hookenv
        self._host = host

    def provide_data(self):
        """Refresh leader data if needed."""
        if not self._hookenv.is_leader():
            return
        data = self._hookenv.leader_get()
        data.setdefault("database-password", self._host.pwgen())
        data.setdefault("secret-token", self._host.pwgen(length=172))
        # We want to overwrite any possible stale value for the leader IP
        data["leader-ip"] = self._hookenv.unit_private_ip()
        self._hookenv.leader_set(data)


# XXX We inherit from RelationContext here to re-use some of its
#     behavior (the _is_ready method that tests that all required_keys are
#     available), althought this is not really a relation. Perhaps charmhelpers
#     should factor out a base class.
class LeaderRequirer(RelationContext):
    """Grab leader data, which is common across all units."""

    name = "leader"
    required_keys = [
        "database-password",  # Password for the 'landscape' database user.
        "secret-token",       # Landscape-wide secret token.
        "leader-ip",          # The leader unit's private address.
    ]

    def __init__(self, hookenv=hookenv):
        self._hookenv = hookenv
        super(LeaderRequirer, self).__init__()

    def is_ready(self):
        ready = bool(self.get(self.name))
        if not ready:
            self._hookenv.log(
                "Incomplete data: {}".format(self.__class__.__name__),
                hookenv.DEBUG)
        return ready

    def get_data(self):
        data = self._hookenv.leader_get()
        if self._is_ready(data):
            # If all required keys are there, let's populate the requirer
            self.setdefault(self.name, data)
