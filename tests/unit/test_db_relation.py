"""
Tests for the DB relation with the PostgreSQL charm.
"""

from unittest.mock import patch

from ops.testing import Context, Relation, State
import pytest

from src.charm import LandscapeServerCharm


@pytest.fixture(autouse=True)
def check_call():
    """
    Patch `check_call` to avoid any real subprocess calls.
    """
    with patch("src.charm.check_call") as p:
        yield p


@pytest.mark.parametrize("event", ("relation_changed", "relation_joined"))
class TestDBRelation:
    """
    Tests for the `db-relation-joined` and `db-relation-changed` events, which use
    the same hook to respond.
    """

    def test_db_provides_configuration(self, event, capture_service_conf):
        """
        If no database configuration is provided through Juju, then use values
        from the DB relation to configure the stores and schema.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation(
            "db",
            remote_units_data={
                0: {
                    "allowed-units": "landscape-server/0",
                    "master": "host=1.2.3.4 password=testpass",
                    "host": "1.2.3.4",
                    "port": "5678",
                    "user": "testuser",
                    "password": "testpass",
                }
            },
        )
        state_in = State(relations=[relation])

        event_handler = getattr(context.on, event)
        context.run(event_handler(relation), state_in)

        service_conf = capture_service_conf.get_config()
        assert service_conf["stores"]["host"] == "1.2.3.4:5678"
        assert service_conf["stores"]["password"] == "testpass"
        assert service_conf["schema"]["store_user"] == "testuser"
        assert service_conf["schema"]["store_password"] == "testpass"

    def test_manual_configs_used(self, event, capture_service_conf):
        """
        If stores and schema passwords are given in the Juju config and the Postgres
        unit also supplies configuration, the Juju configuration takes priority.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation(
            "db",
            remote_units_data={
                0: {
                    "allowed-units": "landscape-server/0",
                    "master": "host=1.2.3.4 password=testpass",
                    "host": "1.2.3.4",
                    "port": "5678",
                    "user": "testuser",
                    "password": "testpass",
                }
            },
        )
        state_in = State(
            config={
                "db_host": "hello",
                "db_port": "world",
                "db_schema_user": "test",
                "db_landscape_password": "test_pass",
                "db_schema_password": "schema_pass",
            },
            relations=[relation],
        )

        event_handler = getattr(context.on, event)
        context.run(event_handler(relation), state_in)

        service_conf = capture_service_conf.get_config()
        assert service_conf["stores"]["host"] == "hello:world"
        assert service_conf["stores"]["password"] == "test_pass"
        assert service_conf["schema"]["store_user"] == "test"
        assert service_conf["schema"]["store_password"] == "schema_pass"

    def test_manual_configs_used_partial(self, event, capture_service_conf):
        """
        If some database configuration is supplied in the Juju config, it is used, and
        the rest is filled in using configuration supplied by the Postgres unit.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation(
            "db",
            remote_units_data={
                0: {
                    "allowed-units": "landscape-server/0",
                    "master": "host=1.2.3.4 password=testpass",
                    "host": "1.2.3.4",
                    "port": "5678",
                    "user": "testuser",
                    "password": "testpass",
                }
            },
        )
        state_in = State(
            config={
                "db_host": "hello",
                "db_port": "world",
            },
            relations=[relation],
        )

        event_handler = getattr(context.on, event)
        context.run(event_handler(relation), state_in)

        service_conf = capture_service_conf.get_config()
        assert service_conf["stores"]["host"] == "hello:world"
        assert service_conf["stores"]["password"] == "testpass"
        assert service_conf["schema"]["store_user"] == "testuser"
        assert service_conf["schema"]["store_password"] == "testpass"
