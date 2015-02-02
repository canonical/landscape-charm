from charmhelpers.core import hookenv
from charmhelpers.core.services.helpers import RelationContext

from lib.relations.errors import UnitDataNotReadyError


class PostgreSQLRequirer(RelationContext):
    """
    Relation context for the `pgsql` interface.
    """
    name = "db"
    interface = "pgsql"
    required_keys = [
        "host",
        "port",
        'user',
        "password",
        "database",
        "allowed-units",
        "state"]

    def __init__(self, hookenv=hookenv):
        self._hookenv = hookenv
        super(PostgreSQLRequirer, self).__init__()

    def _is_ready(self, unit_data):
        """Check that everything is green to start talking to PostgreSQL.

        Beside the started L{RelationContext} check that all required keys are
        set in the relation, we want to ensure some extra constraints specific
        to the postgresql charm (see its REAMDE.md file for details).
        """
        # First call the superclass method to check that the required keys are
        # in the relation at all.
        if not super(PostgreSQLRequirer, self)._is_ready(unit_data):
            return False

        try:
            self._check_allowed_units(unit_data)
            self._check_state(unit_data)
        except UnitDataNotReadyError:
            return False

        return True

    def _check_allowed_units(self, unit_data):
        """Check if we've been allowed access yet.

        From postgresql charm's README.md: "A client may also wish to defer
        its setup until the unit name is listed in 'allowed-units', to avoid
        attempting to connect to a database before it has been authorized.".
        """
        allowed_units = unit_data["allowed-units"].split()
        local_unit = self._hookenv.local_unit()
        if local_unit not in allowed_units:
            self._hookenv.log("%s not in allowed_units yet (%s)" % (
                local_unit, allowed_units))
            raise UnitDataNotReadyError()

    def _check_state(self, unit_data):
        """Check that the postgresql unit at hand is a master one.

        From postgresql charm's README.md: "If there is more than one
        PostgreSQL unit related, the client charm must only use units
        with state set to 'master' or 'hot standby'.".
        """
        ignored_states = set(["hot standby", "failover"])

        # XXX for now we support relating to at most one PostgreSQL service
        #     when we'll support sharding we'll want to account for more
        #     than one master.
        relation_id = self._hookenv.relation_ids(self.name)[0]

        units_count = len(self._hookenv.related_units(relation_id))
        if units_count > 1:
            self._hookenv.log(
                "The postgresql service is clustered with %s units. "
                "Ignoring any intermittent 'standalone' states." % units_count)
            ignored_states.add("standalone")

        state = unit_data["state"]
        if state in ignored_states:
            self._hookenv.log(
                "Discarding postgresql unit with invalid state '%s' for "
                "host %s." % (state, unit_data["host"]))
            raise UnitDataNotReadyError()
