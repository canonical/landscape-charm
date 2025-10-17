import unittest
from subprocess import CalledProcessError
import unittest
from unittest import mock
from unittest.mock import ANY, call, Mock, patch

from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Context, Harness, Relation, State, StoredState


from charms.data_platform_libs.v0.data_interfaces import DatabaseCreatedEvent
from charm import (
    LandscapeServerCharm,
    UPDATE_WSL_DISTRIBUTIONS_SCRIPT,
)
from database import DatabaseConnectionContext, fetch_postgres_relation_data


class TestFetchPostgresRelationData:
    def test_returns_connection_details(self):
        db_manager = mock.Mock()
        db_manager.fetch_relation_data.return_value = {
            1: {
                "endpoints": "1.2.3.4:5432",
                "username": "landscape",
                "password": "secret",
            }
        }
        with mock.patch("src.database.logger"):
            result = fetch_postgres_relation_data(db_manager)

        db_manager.fetch_relation_data.assert_called_once_with()
        assert result == DatabaseConnectionContext(
            host="1.2.3.4",
            port="5432",
            username="landscape",
            password="secret",
        )

    def test_skips_empty_entries(self):
        db_manager = mock.Mock()
        db_manager.fetch_relation_data.return_value = {
            1: {},
            2: {
                "endpoints": "5.6.7.8:6543",
                "username": "reader",
                "password": "hunter2",
            },
        }
        with mock.patch("src.database.logger"):
            result = fetch_postgres_relation_data(db_manager)

        assert result == DatabaseConnectionContext(
            host="5.6.7.8",
            port="6543",
            username="reader",
            password="hunter2",
        )

    def test_returns_empty_context_when_no_data(self):
        db_manager = mock.Mock()
        db_manager.fetch_relation_data.return_value = {}
        with mock.patch("src.database.logger"):
            result = fetch_postgres_relation_data(db_manager)

        assert result == DatabaseConnectionContext()



class TestDatabaseRelation:
    """
    Tests for the modern `postgres_client` interface.
    """

    @staticmethod
    def _state(
        *,
        relation: Relation,
        leader: bool,
        config: dict | None = None,
        ready: dict | None = None,
    ) -> State:
        ready_map = ready or {
            "db": False,
            "inbound-amqp": False,
            "outbound-amqp": False,
            "haproxy": False,
        }
        stored = StoredState(
            owner_path="LandscapeServerCharm",
            content={"ready": ready_map},
        )
        return State(
            relations=[relation],
            leader=leader,
            config=config or {},
            stored_states=[stored],
        )

    def test_database_relation_changed_not_leader(self):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        state_in = self._state(relation=relation, leader=False)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm._database_relation_changed(
                mock.create_autospec(DatabaseCreatedEvent)
            )
            status = manager.charm.unit.status
            ready = dict(manager.charm._stored.ready)

        assert isinstance(status, ActiveStatus)
        assert ready["db"] is True

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=True)
    @patch("charm.LandscapeServerCharm._update_wsl_distributions", return_value=True)
    def test_database_relation_missing_fields(
        self, _, __, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=None, username=None, password="secret"
        )

        state_in = self._state(relation=relation, leader=True)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status") as update_ready:
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )
                status = manager.charm.unit.status
                ready = dict(manager.charm._stored.ready)

        assert isinstance(status, ActiveStatus)
        assert ready["db"] is False
        update_db_conf.assert_not_called()
        update_ready.assert_called_once_with()

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=True)
    @patch("charm.LandscapeServerCharm._update_wsl_distributions", return_value=True)
    def test_database_relation_uses_relation_credentials(
        self, _, __, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=5432, username="landscape", password="secret"
        )

        state_in = self._state(relation=relation, leader=True)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status") as update_ready:
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )
                status = manager.charm.unit.status
                ready = dict(manager.charm._stored.ready)

        update_db_conf.assert_called_once_with(
            host="1.2.3.4",
            port=5432,
            user="landscape",
            password="secret",
            schema_password=None,
        )
        update_ready.assert_called_once_with(restart_services=True)
        assert isinstance(status, ActiveStatus)
        assert ready["db"] is True

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=True)
    @patch("charm.LandscapeServerCharm._update_wsl_distributions", return_value=True)
    def test_database_relation_manual_overrides(
        self, _, __, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=5432, username="landscape", password="secret"
        )

        config = {
            "db_host": "override-host",
            "db_port": "6000",
            "db_schema_user": "schemauser",
            "db_landscape_password": "landscape-pass",
        }
        state_in = self._state(relation=relation, leader=True, config=config)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status") as update_ready:
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )
                status = manager.charm.unit.status
                ready = dict(manager.charm._stored.ready)

        assert isinstance(status, ActiveStatus)
        assert ready["db"] is True
        update_db_conf.assert_called_once_with(
            host="override-host",
            port="6000",
            user="schemauser",
            password="landscape-pass",
            schema_password=None,
        )
        update_ready.assert_called_once_with(restart_services=True)

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=True)
    @patch("charm.LandscapeServerCharm._update_wsl_distributions", return_value=True)
    def test_database_relation_schema_password_override(
        self, _, __, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=5432, username="landscape", password="secret"
        )

        config = {
            "db_schema_password": "override-schema-pass",
        }
        state_in = self._state(relation=relation, leader=True, config=config)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status"):
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )

        update_db_conf.assert_called_once_with(
            host="1.2.3.4",
            port=5432,
            user="landscape",
            password="secret",
            schema_password="override-schema-pass",
        )

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=True)
    @patch("charm.LandscapeServerCharm._update_wsl_distributions", return_value=True)
    def test_database_relation_partial_overrides(
        self, _, __, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=5432, username="landscape", password="secret"
        )

        config = {
            "db_host": "override-host",
        }
        state_in = self._state(relation=relation, leader=True, config=config)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status"):
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )

        update_db_conf.assert_called_once_with(
            host="override-host",
            port=5432,
            user="landscape",
            password="secret",
            schema_password=None,
        )

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=False)
    def test_database_relation_migrate_failure(
        self, _, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=5432, username="landscape", password="secret"
        )

        state_in = self._state(relation=relation, leader=True)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status") as update_ready:
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )
                status = manager.charm.unit.status
                ready = dict(manager.charm._stored.ready)

        update_db_conf.assert_called_once()
        update_ready.assert_not_called()
        assert isinstance(status, MaintenanceStatus)
        assert ready["db"] is False

    @patch("charm.fetch_postgres_relation_data")
    @patch("charm.update_db_conf")
    @patch("charm.LandscapeServerCharm._migrate_schema_bootstrap", return_value=True)
    @patch("charm.LandscapeServerCharm._update_wsl_distributions", return_value=False)
    def test_database_relation_update_wsl_failure(
        self, _, __, update_db_conf, fetch_mock
    ):
        ctx = Context(LandscapeServerCharm)
        relation = Relation("database", remote_app_name="postgresql")
        fetch_mock.return_value = DatabaseConnectionContext(
            host="1.2.3.4", port=5432, username="landscape", password="secret"
        )

        state_in = self._state(relation=relation, leader=True)

        with ctx(ctx.on.start(), state_in) as manager:
            manager.charm.database = Mock()
            with patch.object(manager.charm, "_update_ready_status") as update_ready:
                manager.charm._database_relation_changed(
                    mock.create_autospec(DatabaseCreatedEvent)
                )
                status = manager.charm.unit.status
                ready = dict(manager.charm._stored.ready)

        update_db_conf.assert_called_once()
        update_ready.assert_not_called()
        assert isinstance(status, MaintenanceStatus)
        assert ready["db"] is False


class DbRelationTest(unittest.TestCase):
    """
    Tests for the legacy `pgsql` interface.
    """

    def setUp(self):
        self.harness = Harness(LandscapeServerCharm)
        self.addCleanup(self.harness.cleanup)
        self.log_error_mock = patch("charm.logger.error").start()
        self.log_info_mock = patch("charm.logger.info").start()
        self.addCleanup(patch.stopall)
        self.harness.begin()

    def test_db_relation_changed_no_master(self):
        mock_event = mock.Mock()
        mock_event.relation.data = {mock_event.unit: {}}

        self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertFalse(self.harness.charm._stored.ready["db"])

    def test_db_relation_changed_not_allowed_unit(self):
        mock_event = mock.Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": "",
                "master": True,
            },
        }

        self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertFalse(self.harness.charm._stored.ready["db"])

    def test_db_relation_changed(self):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call"),
            patch("settings_files.update_service_conf") as update_service_conf_mock,
        ):
            self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["db"])

        update_service_conf_mock.assert_called_once_with(
            {
                "stores": {
                    "host": "1.2.3.4:5678",
                    "password": "testpass",
                },
                "schema": {
                    "store_user": "testuser",
                    "store_password": "testpass",
                },
            }
        )

    def test_db_manual_configs_used(self):
        self.harness.disable_hooks()
        self.harness.update_config(
            {
                "db_host": "hello",
                "db_port": "world",
                "db_schema_user": "test",
                "db_landscape_password": "test_pass",
            }
        )
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call"),
            patch("settings_files.update_service_conf") as update_service_conf_mock,
        ):
            self.harness.charm._db_relation_changed(mock_event)

        update_service_conf_mock.assert_called_once_with(
            {
                "stores": {
                    "host": "hello:world",
                    "password": "test_pass",
                },
                "schema": {
                    "store_user": "test",
                    "store_password": "test_pass",
                },
            }
        )

    def test_db_manual_configs_password(self):
        """
        Test specifying both passwords in the juju config
        """
        self.harness.disable_hooks()
        self.harness.update_config(
            {
                "db_host": "hello",
                "db_port": "world",
                "db_schema_user": "test",
                "db_landscape_password": "test_pass",
                "db_schema_password": "schema_pass",
            }
        )
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call"),
            patch("settings_files.update_service_conf") as update_service_conf_mock,
        ):
            self.harness.charm._db_relation_changed(mock_event)

        update_service_conf_mock.assert_called_once_with(
            {
                "stores": {
                    "host": "hello:world",
                    "password": "test_pass",
                },
                "schema": {
                    "store_user": "test",
                    "store_password": "schema_pass",
                },
            }
        )

    def test_db_manual_configs_used_partial(self):
        """
        Test that if some of the manual configs are provided, the rest are
        gotten from the postgres unit
        """
        self.harness.disable_hooks()
        self.harness.update_config({"db_host": "hello", "db_port": "world"})
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call"),
            patch("settings_files.update_service_conf") as update_service_conf_mock,
        ):
            self.harness.charm._db_relation_changed(mock_event)

        update_service_conf_mock.assert_called_once_with(
            {
                "stores": {
                    "host": "hello:world",
                    "password": "testpass",
                },
                "schema": {
                    "store_user": "testuser",
                    "store_password": "testpass",
                },
            }
        )

    def test_db_relation_changed_called_process_error(self):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call") as check_call_mock,
            patch("settings_files.update_service_conf") as update_service_conf_mock,
        ):
            check_call_mock.side_effect = CalledProcessError(127, "ouch")
            self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertFalse(self.harness.charm._stored.ready["db"])

        update_service_conf_mock.assert_called_once_with(
            {
                "stores": {
                    "host": "1.2.3.4:5678",
                    "password": "testpass",
                },
                "schema": {
                    "store_user": "testuser",
                    "store_password": "testpass",
                },
            }
        )

    @patch("charm.update_service_conf")
    def test_on_manual_db_config_change(self, _):
        """
        Test that the manual db settings are reflected if a config change happens later
        """

        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }
        peer_relation_id = self.harness.add_relation("replicas", "landscape-server")
        self.harness.update_relation_data(
            peer_relation_id, "landscape-server", {"leader-ip": "test"}
        )

        with (
            patch("charm.check_call"),
            patch(
                "settings_files.update_service_conf",
            ) as update_service_conf_mock,
        ):
            self.harness.charm._db_relation_changed(mock_event)
            self.harness.update_config({"db_host": "hello", "db_port": "world"})

        self.assertEqual(update_service_conf_mock.call_count, 2)
        self.assertEqual(
            update_service_conf_mock.call_args_list[1],
            call(
                {
                    "stores": {
                        "host": "hello:world",
                    },
                }
            ),
        )

    @patch("charm.update_service_conf")
    def test_on_manual_db_config_change_block_if_error(self, _):
        """
        If the schema migration doesn't go through on a manual config change,
        then block unit status
        """
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call") as check_call_mock,
            patch("settings_files.update_service_conf"),
        ):
            self.harness.charm._db_relation_changed(mock_event)

        with (
            patch("charm.check_call") as check_call_mock,
            patch("settings_files.update_service_conf"),
        ):
            check_call_mock.side_effect = CalledProcessError(127, "ouch")
            self.harness.update_config({"db_host": "hello", "db_port": "world"})

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)

    @patch("charm.update_service_conf")
    def test_on_db_relation_changed_update_wsl_distribution(self, _):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call") as check_call_mock,
            patch("settings_files.update_service_conf"),
        ):
            self.harness.charm._db_relation_changed(mock_event)

        check_call_mock.assert_called_with([UPDATE_WSL_DISTRIBUTIONS_SCRIPT], env=ANY)

    @patch("charm.update_service_conf")
    def test_on_db_relation_update_wsl_distributions_fail(self, _):
        """
        If the `update_wsl_distributions` script fails,
        it will not result in a `BlockedStatus`.
        """
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": "host=1.2.3.4 password=testpass",
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }

        with (
            patch("charm.check_call") as check_call_mock,
            patch("settings_files.update_service_conf"),
        ):
            # Let bootstrap account go through
            check_call_mock.side_effect = [None, CalledProcessError(127, "ouch")]
            self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertNotIsInstance(status, BlockedStatus)

        info_calls = [call.args for call in self.log_info_mock.call_args_list]
        error_calls = [call.args for call in self.log_error_mock.call_args_list]

        self.assertIn(("Updating WSL distributions...",), info_calls)
        self.assertIn(
            (
                "Try updating the stock WSL distributions again later by running '%s'.",
                f"{UPDATE_WSL_DISTRIBUTIONS_SCRIPT}",
            ),
            info_calls,
        )

        self.assertIn(
            ("Failed to update WSL distributions with return code %d", 127),
            error_calls,
        )
