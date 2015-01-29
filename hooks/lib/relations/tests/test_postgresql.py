from lib.tests.helpers import HookenvTest
from lib.tests.sample import SAMPLE_POSTGRESQL_UNIT_DATA
from lib.relations.postgresql import PostgreSQLRelation


class PostgreSQLRelationTest(HookenvTest):

    with_hookenv_monkey_patch = True

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

    def test_local_unit_in_allowed_units(self):
        """
        The L{PostgreSQLRelation} is not ready if the local unit is in
        the 'allowed-units' list.
        """
        unit_data = SAMPLE_POSTGRESQL_UNIT_DATA.copy()
        unit_data["allowed-units"] = ""
        self.hookenv.relations = {
            "db": {
                "db:1": {
                    "postgresql/0": unit_data,
                }
            }
        }

        relation = PostgreSQLRelation(hookenv=self.hookenv)
        self.assertFalse(relation.is_ready())
        self.assertIn(
            ("landscape-server/0 not in allowed_units yet ([])", None),
            self.hookenv.messages)

    def test_discard_non_master_states(self):
        """
        The L{PostgreSQLRelation} is not ready if the remote postgres unit
        is not a 'master'.
        """
        unit_data1 = SAMPLE_POSTGRESQL_UNIT_DATA.copy()
        unit_data1["host"] = "10.0.3.170"
        unit_data1["state"] = "hot standby"
        unit_data2 = SAMPLE_POSTGRESQL_UNIT_DATA.copy()
        unit_data2["host"] = "10.0.3.169"
        unit_data2["state"] = "master"
        unit_data3 = SAMPLE_POSTGRESQL_UNIT_DATA.copy()
        unit_data3["host"] = "10.0.3.171"
        unit_data3["state"] = "standalone"
        self.hookenv.relations = {
            "db": {
                "db:1": {
                    "postgresql/0": unit_data1,
                    "postgresql/1": unit_data2,
                    "postgresql/2": unit_data3,
                }
            }
        }
        relation = PostgreSQLRelation(hookenv=self.hookenv)
        self.assertTrue(relation.is_ready())
        self.assertIn(
            ("Discarding postgresql unit with invalid state 'hot standby' "
             "for host 10.0.3.170.", None),
            self.hookenv.messages)
        self.assertIn(
            ("Discarding postgresql unit with invalid state 'standalone' "
             "for host 10.0.3.171.", None),
            self.hookenv.messages)
        self.assertEqual("10.0.3.169", relation["db"][0]["host"])
