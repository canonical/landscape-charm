import os

from charmhelpers.core.services.helpers import RelationContext, StoredContext
from charmhelpers.core import host
from charmhelpers.contrib.hahelpers import cluster

from lib.hook import HookError


class LandscapeRelation(RelationContext):
    """Relation context for the 'landscape-ha' interface.

    This relation manages information that should flow between Landscape peer
    units.

    Currently it's used exclusively to propagate leader data, so its only key
    is 'leader', which will be set either to local L{LandscapeLeaderContext}
    data (if we are the leader), or to the data provided by the leader peer
    unit using the relation.
    """
    name = "cluster"
    interface = "landscape-ha"
    required_keys = [
        "database-password",  # Password for the 'landscape' database user.
    ]

    _leader_context = None

    def __init__(self, cluster=cluster, host=host):
        if cluster.is_elected_leader(None):
            self._leader_context = LandscapeLeaderContext(host=host)
        super(LandscapeRelation, self).__init__()

    def provide_data(self):
        if not self._leader_context:
            return {}
        return self._leader_context

    def get_data(self):
        super(LandscapeRelation, self).get_data()
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
        return self._is_ready(self.get("leader", {}))


class LandscapeLeaderContext(StoredContext):
    """Hold information for the Landscape unit acting as a leader."""

    def __init__(self, host=host, path="landscape-leader-context.yaml"):
        if os.path.exists(path):
            data = self.read_context(path)
        else:
            data = {"database-password": host.pwgen()}
            self.store_context(path, data)
        self.update(data)
