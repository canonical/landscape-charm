from charmhelpers.core import hookenv
from charmhelpers.core.services.helpers import RelationContext

from lib.relations.errors import UnitDataNotReadyError


class PostgreSQLProvider(RelationContext):
    name = "db"
    interface = "pgsql"

    def __init__(self, database=None):
        super(PostgreSQLProvider, self).__init__()
        self.database = database

    def provide_data(self):
        return {"database": self.database}


class PostgreSQLRequirer(RelationContext):
    """
    Relation context for the `pgsql` interface.
    """
    name = "db"
    interface = "pgsql"
    required_keys = [
        "master",
        "allowed-units"]

    def __init__(self, hookenv=hookenv):
        self._hookenv = hookenv
        super(PostgreSQLRequirer, self).__init__()

    def _is_ready(self, unit_data):
        """Check that everything is green to start talking to PostgreSQL.

        Beside the started L{RelationContext} check that all required keys are
        set in the relation, we want to ensure some extra constraints specific
        to the postgresql charm (see its README.md file for details).
        """
        # First call the superclass method to check that the required keys are
        # in the relation at all.
        if not super(PostgreSQLRequirer, self)._is_ready(unit_data):
            return False

        try:
            self._check_allowed_units(unit_data)
            if not unit_data.get('master'):
                return False
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

    def get_data(self):
        super(PostgreSQLRequirer, self).get_data()
        for n in self.get(self.name, []):
            if n.get("master"):
                n.update(self.parse_dsn(n["master"]))

    def parse_dsn(self, dsn):
        data = {}
        for v in dsn.split(' '):
            key, value = v.split("=")
            if key == 'port':
                value = int(value)
            data[key] = value
        return data

