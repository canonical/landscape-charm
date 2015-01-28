from lib.tests.helpers import HookenvTest
from lib.relations.postgresql import PostgreSQLRelation


class PostgreSQLRelationTest(HookenvTest):

    def test_required_keys(self):
        """
        The L{PostgreSQLRelation} class defines all keys that are required to
        be set on the db relation in order for the relation to be considered
        ready.
        """
        self.assertEqual(
            ["host", "port", "user", "password", "database",
             "allowed-units", "state"],
            PostgreSQLRelation.required_keys)
