from charmhelpers.core.services.helpers import RelationContext


class PostgreSQLRelation(RelationContext):
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
