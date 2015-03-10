import os
from random import SystemRandom
from string import letters, digits

from charmhelpers.core.services.helpers import RelationContext, StoredContext
from charmhelpers.core import host, hookenv

from lib.hook import HookError


class LandscapeProvider(RelationContext):
    """Relation data provider for the 'landscape-ha' interface.

    This relation manages information that should flow between Landscape peer
    units.

    Currently it's used exclusively to propagate leader data.
    """
    name = "cluster"
    interface = "landscape-ha"
    required_keys = [
        "database-password",  # Password for the 'landscape' database user.
    ]

    def __init__(self, leader_context):
        self._leader_context = leader_context

    def provide_data(self):
        return self._leader_context or {}


class LandscapeRequirer(RelationContext):
    """Relation data requirer for the 'landscape-ha' interface.

    This relation acquires information from other Landscape units. Its only
    key is 'leader', which will be set either to the local leader context
    data (if we are the leader), or to the data provided by the leader peer
    unit using the relation.
    """
    name = "cluster"
    interface = "landscape-ha"
    required_keys = [
        "database-password",  # Password for the 'landscape' database user.
    ]

    def __init__(self, leader_context):
        self._leader_context = leader_context
        super(LandscapeRequirer, self).__init__()

    def get_data(self):
        super(LandscapeRequirer, self).get_data()
        data = self.pop(self.name, [])
        leader_count = len(data)
        if self._leader_context:
            # In case we are the leader, we don't need the information from a
            # remote leader, and we rather provide the information that we
            # store locally with the LandscapeLeaderContext class.
            leader_count += 1
        if leader_count > 1:
            raise HookError("Split brain detected in leader election")
        elif leader_count == 1:
            self["leader"] = self._leader_context or data[0]

    def is_ready(self):
        # The relation is considered ready only if we got leader data
        ready = self._is_ready(self.get("leader", {}))
        if not ready:
            # XXX copied from charmhelpers, it would be nice to extract it into
            #     some standalone private method, for re-use in subclasses.
            hookenv.log(
                "Incomplete relation: {}".format(self.__class__.__name__),
                hookenv.DEBUG)
        return ready


class LandscapeLeaderContext(StoredContext):
    """Hold information for the Landscape unit acting as a leader."""

    @staticmethod
    def _generate_secret_token():
        """
        Generate a string with 1024 bits of entropy.

        Using 172 * the 62 possible alphanumerics [a-z][A-Z][0-9] provides:
        math.log(62, 2) * 172 ~= 1024 bits of entropy.
        """
        random_chooser = SystemRandom()
        alphanumerics = letters[0:52] + digits
        return "".join(random_chooser.choice(alphanumerics)
                       for _ in range(172))

    def __init__(self, host=host, path="landscape-leader-context.yaml"):
        if os.path.exists(path):
            data = self.read_context(path)
        else:
            data = {"database-password": host.pwgen(),
                    "secret-token": self._generate_secret_token()}
            self.store_context(path, data)
        self.update(data)
