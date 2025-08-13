# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

from base64 import b64encode
from dataclasses import asdict
import json
import os
import unittest
from grp import struct_group
from io import BytesIO
from pwd import struct_passwd
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Iterable
from unittest.mock import DEFAULT, Mock, patch, call, ANY

import yaml

from ops import testing
from ops.charm import ActionEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Context, Harness, Relation, State

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v0.apt import PackageError, PackageNotFoundError

from charm import (
    _create_haproxy_services,
    DEFAULT_SERVICES,
    HAPROXY_CONFIG_FILE,
    HAProxyErrorFile,
    HAProxyServicePorts,
    HAProxyServerOptions,
    LANDSCAPE_PACKAGES,
    LEADER_SERVICES,
    LSCTL,
    NRPE_D_DIR,
    SCHEMA_SCRIPT,
    HASH_ID_DATABASES,
    LandscapeServerCharm,
    get_modified_env_vars,
    METRIC_INSTRUMENTED_SERVICE_PORTS,
)


IS_CI = os.getenv("GITHUB_ACTIONS", None) is not None
"""
GitHub actions will set `GITHUB_ACTIONS` during runs.
"""


class TestGrafanaMachineAgentRelation(unittest.TestCase):

    def _get_cos_agent_relation_config(self, state: State) -> dict:
        """
        Extract the cos-agent relation configuration.
        """
        for relation in state.relations:
            if relation.endpoint == "cos-agent":
                break
        else:
            raise ValueError("No cos-agent relation found.")

        return json.loads(relation.local_unit_data["config"])

    def test_relation(self):
        """
        Landscape provides configuration to the `cos-agent` relation when joined.

        Landscape provides metrics scrape jobs and metrics alert rules to the relation.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation("cos-agent")
        state = State(relations=[relation])

        result = context.run(context.on.relation_joined(relation), state)
        config = self._get_cos_agent_relation_config(result)

        self.assertIn("metrics_scrape_jobs", config)
        self.assertIn("metrics_alert_rules", config)

    def test_metrics_scrape_configs(self):
        """
        Landscape provides scrape configs for each instrumented Landscape service.
        """

        context = Context(LandscapeServerCharm)
        relation = Relation("cos-agent")
        state = State(relations=[relation])

        result = context.run(context.on.relation_joined(relation), state)
        config = self._get_cos_agent_relation_config(result)

        self.assertIn("metrics_scrape_jobs", config)
        scrape_jobs = config["metrics_scrape_jobs"]

        expected_static_configs = [
            {
                "targets": [f"localhost:{port}"],
                "labels": {"landscape_service": f"{service}"},
            }
            for service, port in METRIC_INSTRUMENTED_SERVICE_PORTS
        ]

        actual_static_configs = [scrape["static_configs"][0] for scrape in scrape_jobs]

        self.assertListEqual(expected_static_configs, actual_static_configs)

    def test_scrape_interval(self):
        """
        Landscape exposes a Prometheus scrape interval configuration parameter
        and forwards it to the relation.
        """
        scrape_interval = "5m"
        context = Context(LandscapeServerCharm)
        relation = Relation("cos-agent")
        state = State(
            relations=[relation],
            config={"prometheus_scrape_interval": scrape_interval},
        )

        result = context.run(context.on.relation_joined(relation), state)
        config = self._get_cos_agent_relation_config(result)

        for scrape_job in config["metrics_scrape_jobs"]:
            self.assertEqual(scrape_interval, scrape_job["scrape_interval"])


from settings_files import AMQP_USERNAME, VHOSTS
from src.charm import UPDATE_WSL_DISTRIBUTIONS_SCRIPT


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(LandscapeServerCharm)
        self.addCleanup(self.harness.cleanup)

        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        pwd_mock = patch("charm.user_exists").start()
        pwd_mock.return_value = Mock(spec_set=struct_passwd, pw_uid=1000)
        grp_mock = patch("charm.group_exists").start()
        grp_mock.return_value = Mock(spec_set=struct_group, gr_gid=1000)

        patch("charm.service_pause").start()
        patch("charm.service_reload").start()
        patch("charm.service_resume").start()
        patch("charm.service_running").start()
        patch("charm.service_running").start()

        self.log_error_mock = patch("charm.logger.error").start()
        self.log_info_mock = patch("charm.logger.info").start()

        self.addCleanup(patch.stopall)

        self.harness.begin()

    def test_init(self):
        self.assertEqual(
            self.harness.charm._stored.ready,
            {
                "db": False,
                "inbound-amqp": False,
                "outbound-amqp": False,
                "haproxy": False,
            },
        )

    def test_install(self):
        harness = Harness(LandscapeServerCharm)
        relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"}
        )

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            prepend_default_settings=DEFAULT,
            update_service_conf=DEFAULT,
        )
        ppa = harness.model.config.get("landscape_ppa")
        env_variables = os.environ.copy()

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["check_call"].assert_any_call(
            ["add-apt-repository", "-y", ppa], env=env_variables
        )
        mocks["check_call"].assert_any_call(["apt-mark", "hold", "landscape-server"])
        mocks["apt"].add_package.assert_called_once_with(
            ["landscape-server", "landscape-hashids"],
            update_cache=True,
        )
        status = harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertEqual(
            status.message,
            "Waiting on relations: db, inbound-amqp, outbound-amqp, haproxy",
        )

    def test_install_package_not_found_error(self):
        harness = Harness(LandscapeServerCharm)
        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            update_service_conf=DEFAULT,
        )

        relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"}
        )

        with patches as mocks:
            mocks["apt"].add_package.side_effect = PackageNotFoundError
            self.assertRaises(PackageNotFoundError, harness.begin_with_initial_hooks)

    def test_install_package_error(self):
        harness = Harness(LandscapeServerCharm)
        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            update_service_conf=DEFAULT,
        )

        relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"}
        )

        with patches as mocks:
            mocks["apt"].add_package.side_effect = PackageError("ouch")
            self.assertRaises(PackageError, harness.begin_with_initial_hooks)

    @unittest.skipIf(IS_CI, "Fails in CI for unknown reason. TODO FIXME.")
    def test_install_called_process_error(self):
        harness = Harness(LandscapeServerCharm)
        relation_id = harness.add_relation("replicas", "landcape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"}
        )

        with patch("charm.check_call") as mock:
            with patch("charm.update_service_conf"):
                mock.side_effect = CalledProcessError(127, Mock())
                self.assertRaises(CalledProcessError, harness.begin_with_initial_hooks)

    @patch.dict(
        os.environ,
        {
            "JUJU_CHARM_HTTP_PROXY": "http://proxy.test:3128",
            "JUJU_CHARM_HTTPS_PROXY": "http://proxy-https.test:3128",
        },
    )
    def test_install_add_apt_repository_with_proxy(self):
        harness = Harness(LandscapeServerCharm)
        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            update_service_conf=DEFAULT,
            prepend_default_settings=DEFAULT,
        )
        env_variables = os.environ.copy()
        env_variables["http_proxy"] = "http://proxy.test:3128"
        env_variables["https_proxy"] = "http://proxy-https.test:3128"
        ppa = harness.model.config.get("landscape_ppa")

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["check_call"].assert_any_call(
            ["add-apt-repository", "-y", ppa], env=env_variables
        )

    def test_install_ssl_cert(self):
        harness = Harness(LandscapeServerCharm)
        harness.disable_hooks()
        harness.update_config({"ssl_cert": "MYFANCYCERT="})

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            write_ssl_cert=DEFAULT,
            update_service_conf=DEFAULT,
            prepend_default_settings=DEFAULT,
        )

        peer_relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            peer_relation_id, "landscape-server", {"leader-ip": "test"}
        )

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["write_ssl_cert"].assert_any_call("MYFANCYCERT=")
        mocks["prepend_default_settings"].assert_called_once_with(
            {"DEPLOYED_FROM": "charm"}
        )

    def test_install_license_file(self):
        harness = Harness(LandscapeServerCharm)
        mock_input = os.path.join(self.tempdir.name, "new_license.txt")

        harness.update_config({"license_file": "file://" + mock_input})
        relation_id = harness.add_relation("replicas", "landcape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"}
        )

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            write_license_file=DEFAULT,
            prepend_default_settings=DEFAULT,
            update_service_conf=DEFAULT,
        )

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["write_license_file"].assert_any_call(f"file://{mock_input}", 1000, 1000)

    def test_install_license_file_b64(self):
        harness = Harness(LandscapeServerCharm)
        license_text = "VEhJUyBJUyBBIExJQ0VOU0U"
        harness.update_config({"license_file": license_text})
        relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"}
        )

        with patch.multiple(
            "charm",
            apt=DEFAULT,
            check_call=DEFAULT,
            update_service_conf=DEFAULT,
            prepend_default_settings=DEFAULT,
            write_license_file=DEFAULT,
        ) as mocks:
            harness.begin_with_initial_hooks()

        mock_write = mocks["write_license_file"]
        self.assertEqual(len(mock_write.mock_calls), 2)
        self.assertEqual(mock_write.mock_calls[0].args, (license_text, 1000, 1000))
        self.assertEqual(mock_write.mock_calls[1].args, (license_text, 1000, 1000))

    def test_update_ready_status_not_running(self):
        self.harness.charm.unit.status = WaitingStatus()

        self.harness.charm._stored.ready.update(
            {k: True for k in self.harness.charm._stored.ready.keys()}
        )

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            update_default_settings=DEFAULT,
        )

        with patches as mocks:
            self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, ActiveStatus)
        self.assertEqual(status.message, "Unit is ready")
        self.assertTrue(self.harness.charm._stored.running)

        mock_args = mocks["update_default_settings"].mock_calls[0].args[0]
        self.assertEqual(mock_args["RUN_APPSERVER"], "2")

    def test_update_ready_status_running(self):
        self.harness.charm.unit.status = WaitingStatus()

        self.harness.charm._stored.ready.update(
            {k: True for k in self.harness.charm._stored.ready.keys()}
        )
        self.harness.charm._stored.running = True

        self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, ActiveStatus)
        self.assertEqual(status.message, "Unit is ready")

    def test_update_ready_status_called_process_error(self):
        self.harness.charm.unit.status = WaitingStatus()

        self.harness.charm._stored.ready.update(
            {k: True for k in self.harness.charm._stored.ready.keys()}
        )

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            update_default_settings=DEFAULT,
        )

        with patches as mocks:
            mocks["check_call"].side_effect = CalledProcessError(127, "ouch")
            self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to start services")
        self.assertFalse(self.harness.charm._stored.running)

        mock_args = mocks["update_default_settings"].mock_calls[0].args[0]
        self.assertEqual(mock_args["RUN_APPSERVER"], "2")

    def test_db_relation_changed_no_master(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {}}

        self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertFalse(self.harness.charm._stored.ready["db"])

    def test_db_relation_changed_not_allowed_unit(self):
        mock_event = Mock()
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

        with patch("charm.check_call") as check_call_mock:
            with patch(
                "settings_files.update_service_conf"
            ) as update_service_conf_mock:
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

        with patch("charm.check_call") as check_call_mock:
            with patch(
                "settings_files.update_service_conf"
            ) as update_service_conf_mock:
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

        with patch("charm.check_call") as check_call_mock:
            with patch(
                "settings_files.update_service_conf"
            ) as update_service_conf_mock:
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

        with patch("charm.check_call") as check_call_mock:
            with patch(
                "settings_files.update_service_conf"
            ) as update_service_conf_mock:
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

        with patch("charm.check_call") as check_call_mock:
            with patch(
                "settings_files.update_service_conf"
            ) as update_service_conf_mock:
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

        with patch("charm.check_call"):
            with patch(
                "settings_files.update_service_conf",
            ) as update_service_conf_mock:
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

        with patch("charm.check_call") as check_call_mock:
            with patch("settings_files.update_service_conf"):
                self.harness.charm._db_relation_changed(mock_event)

        with patch("charm.check_call") as check_call_mock:
            with patch("settings_files.update_service_conf"):
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

        with patch("charm.check_call") as check_call_mock:
            with patch("settings_files.update_service_conf"):
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

        with patch("charm.check_call") as check_call_mock:
            with patch("settings_files.update_service_conf"):
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

    def test_inbound_amqp_relation_joined(self):
        """
        The inbound vhost is created.
        """
        unit = self.harness.charm.unit
        mock_event = Mock()
        relation_name = "inbound-amqp"
        mock_event.relation.name = relation_name
        mock_event.relation.data = {unit: {}}

        self.harness.charm._amqp_relation_joined(mock_event)

        self.assertEqual(mock_event.relation.data[unit]["username"], AMQP_USERNAME)
        self.assertEqual(mock_event.relation.data[unit]["vhost"], VHOSTS[relation_name])

    def test_outbound_amqp_relation_joined(self):
        """
        The outbound vhost is created.
        """
        unit = self.harness.charm.unit
        mock_event = Mock()
        relation_name = "outbound-amqp"
        mock_event.relation.name = relation_name
        mock_event.relation.data = {unit: {}}

        self.harness.charm._amqp_relation_joined(mock_event)

        self.assertEqual(mock_event.relation.data[unit]["username"], AMQP_USERNAME)
        self.assertEqual(mock_event.relation.data[unit]["vhost"], VHOSTS[relation_name])

    def test_amqp_relation_changed_no_password(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {}}
        initial_status = self.harness.charm.unit.status

        self.harness.charm._amqp_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertEqual(status, initial_status)
        self.assertFalse(self.harness.charm._stored.ready["outbound-amqp"])
        self.assertFalse(self.harness.charm._stored.ready["inbound-amqp"])

    def test_amqp_relation_changed(self):
        """
        Tests proper handling when the event's hostname
        is a list of strings.
        """
        hostname = ["test1", "test2"]
        password = "testpass"

        outbound_change_event = Mock()
        outbound_change_event.relation.name = "outbound-amqp"
        outbound_change_event.relation.data = {
            outbound_change_event.unit: {
                "hostname": hostname,
                "password": password,
            },
        }

        inbound_change_event = Mock()
        inbound_change_event.relation.name = "inbound-amqp"
        inbound_change_event.relation.data = {
            inbound_change_event.unit: {
                "hostname": hostname,
                "password": password,
            },
        }

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.charm._amqp_relation_changed(inbound_change_event)
            self.harness.charm._amqp_relation_changed(outbound_change_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["inbound-amqp"])
        self.assertTrue(self.harness.charm._stored.ready["outbound-amqp"])

        mock_update_conf.assert_called_once_with(
            {
                "broker": {
                    "host": ",".join(hostname),
                    "password": password,
                },
            }
        )

    def test_amqp_relation_changed_outbound_first(self):
        """
        Tests proper handling when the event's hostname is a single string
        and the outbound amqp relation changes first.
        """
        hostname = "test"
        password = "testpass"

        outbound_change_event = Mock()
        outbound_change_event.relation.name = "outbound-amqp"
        outbound_change_event.relation.data = {
            outbound_change_event.unit: {
                "hostname": hostname,
                "password": password,
            },
        }

        inbound_change_event = Mock()
        inbound_change_event.relation.name = "inbound-amqp"
        inbound_change_event.relation.data = {
            inbound_change_event.unit: {
                "hostname": hostname,
                "password": password,
            },
        }

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.charm._amqp_relation_changed(outbound_change_event)
            self.harness.charm._amqp_relation_changed(inbound_change_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["inbound-amqp"])
        self.assertTrue(self.harness.charm._stored.ready["outbound-amqp"])

        mock_update_conf.assert_called_once_with(
            {
                "broker": {
                    "host": hostname,
                    "password": password,
                },
            }
        )

    def test_website_relation_joined_cert_no_key(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {"public-address": "8.8.8.8"}}
        self.harness.disable_hooks()
        self.harness.update_config({"ssl_cert": "NOTDEFAULT", "ssl_key": ""})

        with patch("charm.update_service_conf"):
            self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(
            status.message, "`ssl_cert` is specified but `ssl_key` is missing"
        )

    def test_website_relation_joined_cert_not_DEFAULT_not_b64(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {"public-address": "8.8.8.8"}}
        self.harness.disable_hooks()
        self.harness.update_config({"ssl_cert": "NOTDEFAULT", "ssl_key": "a"})

        with patch("charm.update_service_conf"):
            self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(
            status.message,
            "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded",
        )

    def test_website_relation_joined_cert_not_DEFAULT_key_not_b64(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {"public-address": "8.8.8.8"}}
        self.harness.disable_hooks()
        self.harness.update_config(
            {
                "ssl_cert": "Tk9UREVGQVVMVA==",
                "ssl_key": "NOTBASE64OHNO",
            }
        )

        with patch("charm.update_service_conf"):
            self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(
            status.message,
            "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded",
        )

    def test_website_relation_joined_cert_not_DEFAULT(self):
        mock_event = Mock()
        mock_event.relation.data = {
            self.harness.charm.unit: {
                "private-address": "192.168.0.1",
            },
            mock_event.unit: {"public-address": "8.8.8.8"},
        }
        self.harness.disable_hooks()
        self.harness.update_config(
            {
                "ssl_cert": "VEhJUyBJUyBBIENFUlQ=",
                "ssl_key": "VEhJUyBJUyBBIEtFWQ==",
            }
        )

        with open(HAPROXY_CONFIG_FILE) as haproxy_config_file:
            haproxy_config = yaml.safe_load(haproxy_config_file)

        haproxy_config["error_files"]["location"] = self.tempdir.name

        for code, filename in haproxy_config["error_files"]["files"].items():
            with open(os.path.join(self.tempdir.name, filename), "w") as error_file:
                error_file.write("THIS IS ERROR FILE FOR {}\n".format(code))

        mock_haproxy_config = os.path.join(self.tempdir.name, "my-haproxy-config.yaml")

        with open(mock_haproxy_config, "w") as mock_haproxy_config_file:
            yaml.safe_dump(haproxy_config, mock_haproxy_config_file)

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        status = self.harness.charm.unit.status
        self.assertIn("services", relation_data)
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["haproxy"])

    def test_website_relation_joined(self):
        mock_event = Mock()
        mock_event.relation.data = {
            self.harness.charm.unit: {"private-address": "192.168.0.1"},
            mock_event.unit: {"public-address": "8.8.8.8"},
        }

        with open(HAPROXY_CONFIG_FILE) as haproxy_config_file:
            haproxy_config = yaml.safe_load(haproxy_config_file)

        haproxy_config["error_files"]["location"] = self.tempdir.name

        for code, filename in haproxy_config["error_files"]["files"].items():
            with open(os.path.join(self.tempdir.name, filename), "w") as error_file:
                error_file.write("THIS IS ERROR FILE FOR {}\n".format(code))

        mock_haproxy_config = os.path.join(self.tempdir.name, "my-haproxy-config.yaml")

        with open(mock_haproxy_config, "w") as mock_haproxy_config_file:
            yaml.safe_dump(haproxy_config, mock_haproxy_config_file)

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        status = self.harness.charm.unit.status
        self.assertIn("services", relation_data)
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["haproxy"])

    def test_website_relation_changed_cert_not_DEFAULT(self):
        mock_event = Mock()
        self.harness.disable_hooks()
        self.harness.update_config({"ssl_cert": "NOTDEFAULT"})
        initial_status = self.harness.charm.unit.status

        with patch("charm.write_ssl_cert") as write_cert_mock:
            self.harness.charm._website_relation_changed(mock_event)

        self.assertEqual(initial_status, self.harness.charm.unit.status)
        write_cert_mock.assert_not_called()

    def test_website_relation_changed_no_new_cert(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {}}
        initial_status = self.harness.charm.unit.status

        with patch("charm.write_ssl_cert") as write_cert_mock:
            self.harness.charm._website_relation_changed(mock_event)

        self.assertEqual(initial_status, self.harness.charm.unit.status)
        write_cert_mock.assert_not_called()

    def test_website_relation_changed(self):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {"ssl_cert": "FANCYNEWCERT"},
            self.harness.charm.unit: {
                "private-address": "test",
                "public-address": "test2",
            },
        }

        old_open = open

        def open_error_file(path, *args, **kwargs):
            if "offline" in path:
                return BytesIO(b"")

            return old_open(path, *args, **kwargs)

        with patch.multiple(
            "charm",
            write_ssl_cert=DEFAULT,
            update_service_conf=DEFAULT,
        ) as mocks:
            write_cert_mock = mocks["write_ssl_cert"]

            with patch("builtins.open") as open_mock:
                open_mock.side_effect = open_error_file
                self.harness.charm._website_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        write_cert_mock.assert_called_once_with("FANCYNEWCERT")

    def test_website_relation_changed_strip_b_char(self):
        self.harness.charm._update_haproxy_connection = Mock()
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {"ssl_cert": "b'FANCYNEWCERT'"},
            self.harness.charm.unit: {
                "private-address": "test",
                "public-address": "test2",
            },
        }

        with patch.multiple(
            "charm",
            write_ssl_cert=DEFAULT,
            update_service_conf=DEFAULT,
        ) as mocks:
            write_cert_mock = mocks["write_ssl_cert"]
            self.harness.charm._website_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        write_cert_mock.assert_called_once_with("FANCYNEWCERT")

    @patch("charm.update_service_conf")
    def test_on_config_changed_no_smtp_change(self, _):
        self.harness.charm._update_ready_status = Mock()
        self.harness.charm._configure_smtp = Mock()
        peer_relation_id = self.harness.add_relation("replicas", "landscape-server")
        self.harness.update_relation_data(
            peer_relation_id, "landscape-server", {"leader-ip": "test"}
        )

        self.harness.update_config({"smtp_relay_host": ""})

        self.harness.charm._configure_smtp.assert_not_called()
        self.assertEqual(self.harness.charm._update_ready_status.call_count, 2)

    @patch("charm.update_service_conf")
    def test_on_config_changed_smtp_change(self, _):
        self.harness.charm._update_ready_status = Mock()
        self.harness.charm._configure_smtp = Mock()
        peer_relation_id = self.harness.add_relation("replicas", "landscape-server")
        self.harness.update_relation_data(
            peer_relation_id, "landscape-server", {"leader-ip": "test"}
        )

        self.harness.update_config({"smtp_relay_host": "smtp.example.com"})

        self.harness.charm._configure_smtp.assert_called_once_with("smtp.example.com")
        self.assertEqual(self.harness.charm._update_ready_status.call_count, 2)

    def test_configure_smtp_relay_host(self):
        mock_postfix_cf = os.path.join(self.tempdir.name, "my_postfix.cf")
        with open(mock_postfix_cf, "w") as mock_postfix_cf_file:
            mock_postfix_cf_file.write("relayhost = \nothersetting = nada\n")

        patches = patch.multiple(
            "charm",
            service_reload=DEFAULT,
            POSTFIX_CF=mock_postfix_cf,
        )

        with patches as mocks:
            self.harness.charm._configure_smtp("smtp.example.com")

        mocks["service_reload"].assert_called_once_with("postfix")
        with open(mock_postfix_cf) as mock_postfix_cf_file:
            self.assertEqual(
                "relayhost = smtp.example.com\n" "othersetting = nada\n",
                mock_postfix_cf_file.read(),
            )

    def test_configure_smtp_relay_host_reload_error(self):
        mock_postfix_cf = os.path.join(self.tempdir.name, "my_postfix.cf")
        with open(mock_postfix_cf, "w") as mock_postfix_cf_file:
            mock_postfix_cf_file.write("relayhost = \nothersetting = nada\n")

        patches = patch.multiple(
            "charm",
            service_reload=DEFAULT,
            POSTFIX_CF=mock_postfix_cf,
        )

        with patches as mocks:
            mocks["service_reload"].return_value = False
            self.harness.charm._configure_smtp("smtp.example.com")

        mocks["service_reload"].assert_called_once_with("postfix")
        with open(mock_postfix_cf) as mock_postfix_cf_file:
            self.assertEqual(
                "relayhost = smtp.example.com\n" "othersetting = nada\n",
                mock_postfix_cf_file.read(),
            )
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test_action_pause(self):
        with patch("charm.check_call") as check_call_mock:
            self.harness.charm._pause(Mock())

        check_call_mock.assert_called_once_with([LSCTL, "stop"], env=ANY)
        self.assertFalse(self.harness.charm._stored.running)

    def test_action_pause_CalledProcessError(self):
        self.harness.charm._stored.running = True
        event = Mock(spec_set=ActionEvent)

        with patch("charm.check_call") as check_call_mock:
            check_call_mock.side_effect = CalledProcessError(127, "ouch")
            self.harness.charm._pause(event)

        check_call_mock.assert_called_once_with([LSCTL, "stop"], env=ANY)
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)
        self.assertTrue(self.harness.charm._stored.running)
        event.fail.assert_called_once()

    def test_action_resume(self):
        self.harness.charm._update_ready_status = Mock()
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            with patch("charm.check_call") as check_call_mock:
                self.harness.charm._resume(event)

        run_mock.assert_called_once_with(
            [LSCTL, "start"], capture_output=True, text=True, env=ANY
        )
        check_call_mock.assert_called_once_with([LSCTL, "status"], env=ANY)
        self.harness.charm._update_ready_status.assert_called_once()
        self.assertTrue(self.harness.charm._stored.running)
        event.log.assert_called_once()

    def test_action_resume_CalledProcessError(self):
        self.harness.charm._update_ready_status = Mock()
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            with patch("charm.check_call") as check_call_mock:
                run_mock.return_value = Mock(stdout="Everything is on fire")
                check_call_mock.side_effect = CalledProcessError(127, "uhoh")

                self.harness.charm._resume(event)

        self.assertEqual(2, len(run_mock.mock_calls))
        run_mock.assert_any_call(
            [LSCTL, "start"], capture_output=True, text=True, env=ANY
        )
        run_mock.assert_any_call([LSCTL, "stop"], env=ANY)
        check_call_mock.assert_called_once_with([LSCTL, "status"], env=ANY)
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)
        event.log.assert_called_once()
        event.fail.assert_called_once()

    def test_action_upgrade(self):
        event = Mock(spec_set=ActionEvent)
        self.harness.charm._stored.running = False
        prev_status = self.harness.charm.unit.status

        with patch("charm.apt", spec_set=apt) as apt_mock, patch("charm.check_call"):
            pkg_mock = Mock()
            apt_mock.DebianPackage.from_apt_cache.return_value = pkg_mock
            self.harness.charm._upgrade(event)

        self.assertGreaterEqual(event.log.call_count, 5)
        self.assertEqual(
            apt_mock.DebianPackage.from_apt_cache.call_count, len(LANDSCAPE_PACKAGES)
        )
        self.assertEqual(pkg_mock.ensure.call_count, len(LANDSCAPE_PACKAGES))
        self.assertEqual(self.harness.charm.unit.status, prev_status)

    def test_action_upgrade_running(self):
        """
        Tests that we do not perform an upgrade while Landscape is running.
        """
        event = Mock(spec_set=ActionEvent)
        self.harness.charm._stored.running = True

        with patch("charm.apt", spec_set=apt) as apt_mock:
            self.harness.charm._upgrade(event)

        event.log.assert_not_called()
        event.fail.assert_called_once()
        apt_mock.add_package.assert_not_called()

    def test_action_upgrade_PackageError(self):
        event = Mock(spec_set=ActionEvent)
        self.harness.charm._stored.running = False

        with patch("charm.apt", spec_set=apt) as apt_mock, patch("charm.check_call"):
            pkg_mock = Mock()
            apt_mock.DebianPackage.from_apt_cache.return_value = pkg_mock
            pkg_mock.ensure.side_effect = PackageNotFoundError("ouch")
            self.harness.charm._upgrade(event)

        self.assertEqual(event.log.call_count, 2)
        event.fail.assert_called_once()
        apt_mock.DebianPackage.from_apt_cache.assert_called_once_with(
            "landscape-server"
        )
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test_action_migrate_schema(self):
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            self.harness.charm._migrate_schema(event)

        event.log.assert_called_once()
        event.fail.assert_not_called()
        run_mock.assert_called_once_with(
            [SCHEMA_SCRIPT], check=True, text=True, env=ANY
        )

    def test_action_migrate_schema_running(self):
        """
        Test that we do not perform a schema migration while Landscape is
        running.
        """
        event = Mock(spec_set=ActionEvent)
        self.harness.charm._stored.running = True

        with patch("subprocess.run") as run_mock:
            self.harness.charm._migrate_schema(event)

        event.log.assert_not_called()
        event.fail.assert_called_once()
        run_mock.assert_not_called()

    def test_action_migrate_schema_CalledProcessError(self):
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            run_mock.side_effect = CalledProcessError(127, "uhoh")
            self.harness.charm._migrate_schema(event)

        event.log.assert_called_once()
        event.fail.assert_called_once()
        run_mock.assert_called_once_with(
            [SCHEMA_SCRIPT], check=True, text=True, env=ANY
        )
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test_nrpe_external_master_relation_joined(self):
        mock_event = Mock()
        mock_event.relation.data = {self.harness.charm.unit: {}}
        mock_nrpe_d_dir = os.path.join(self.tempdir.name, "nrpe.d")
        os.mkdir(mock_nrpe_d_dir)

        self.harness.add_relation("replicas", "landscape-server")
        self.harness.model.get_binding = Mock(
            return_value=Mock(bind_address="123.123.123.123")
        )
        self.harness.charm._update_service_conf = Mock()

        with patch("charm.update_service_conf"):
            self.harness.set_leader()

        with patch("charm.NRPE_D_DIR", new=mock_nrpe_d_dir):
            self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        for service in DEFAULT_SERVICES + LEADER_SERVICES:
            self.assertIn(
                service, mock_event.relation.data[self.harness.charm.unit]["monitors"]
            )

        cfg_files = os.listdir(mock_nrpe_d_dir)
        self.assertEqual(len(DEFAULT_SERVICES + LEADER_SERVICES), len(cfg_files))

    def test_nrpe_external_master_relation_joined_not_leader(self):
        mock_event = Mock()
        unit = self.harness.charm.unit
        mock_event.relation.data = {unit: {}}

        self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        event_data = mock_event.relation.data[unit]

        for service in DEFAULT_SERVICES:
            self.assertIn(service, event_data["monitors"])

        for service in LEADER_SERVICES:
            self.assertNotIn(service, event_data["monitors"])

    def test_nrpe_external_master_relation_joined_cfgs_exist(self):
        mock_event = Mock()
        unit = self.harness.charm.unit
        mock_event.relation.data = {unit: {}}

        self.harness.add_relation("replicas", "landscape-server")
        self.harness.model.get_binding = Mock(
            return_value=Mock(bind_address="123.123.123.123")
        )
        self.harness.charm._update_service_conf = Mock()

        with patch("charm.update_service_conf"):
            self.harness.set_leader()

        with patch("os.path.exists") as os_path_exists_mock:
            os_path_exists_mock.return_value = True
            self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        self.assertEqual(
            len(os_path_exists_mock.mock_calls),
            len(DEFAULT_SERVICES + LEADER_SERVICES) + 1,
        )

    def test_nrpe_external_master_relation_joined_cfgs_exist_not_leader(self):
        mock_event = Mock()
        unit = self.harness.charm.unit
        mock_event.relation.data = {unit: {}}

        with patch("os.path.exists") as os_path_exists_mock:
            with patch("os.remove") as os_remove_mock:
                os_path_exists_mock.return_value = True
                self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        self.assertEqual(
            len(os_path_exists_mock.mock_calls),
            len(DEFAULT_SERVICES + LEADER_SERVICES) + 1,
        )
        self.assertEqual(len(os_remove_mock.mock_calls), len(LEADER_SERVICES))

    def test_nrpe_external_master_relation_joined_cfgs_not_exist_not_leader(self):
        mock_event = Mock()
        unit = self.harness.charm.unit
        mock_event.relation.data = {unit: {}}
        n = 1

        def path_exists(path):
            nonlocal n

            if path == NRPE_D_DIR:
                return True
            elif n <= len(DEFAULT_SERVICES):
                n += 1
                return True

            return False

        with patch("os.path.exists") as os_path_exists_mock:
            with patch("os.remove") as os_remove_mock:
                os_path_exists_mock.side_effect = path_exists
                self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        self.assertEqual(
            len(os_path_exists_mock.mock_calls),
            len(DEFAULT_SERVICES + LEADER_SERVICES) + 1,
        )
        self.assertEqual(len(os_remove_mock.mock_calls), 0)

    def test_on_replicas_relation_changed_leader(self):
        """
        Tests that _update_nrpe_checks is called when leader settings
        have changed and an nrpe-external-master relation exists.
        """
        self.harness.charm._update_nrpe_checks = Mock()
        self.harness.charm._update_haproxy_connection = Mock()
        self.harness.hooks_disabled()
        self.harness.add_relation("nrpe-external-master", "nrpe")
        self.harness.add_relation("website", "haproxy")
        relation_id = self.harness.add_relation("replicas", "landscape-server")

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.set_leader()
            self.harness.update_relation_data(
                relation_id, "landscape-server", {"leader-ip": "test"}
            )

        self.harness.charm._update_nrpe_checks.assert_called_once()
        self.harness.charm._update_haproxy_connection.assert_called_once()
        mock_update_conf.assert_called_once_with(
            {
                "package-search": {
                    "host": "localhost",
                },
            }
        )

    def test_on_replicas_relation_changed_non_leader(self):
        """
        Tests that _update_nrpe_checks is called when leader settings
        have changed and an nrpe-external-master relation exists.
        """
        self.harness.charm._update_nrpe_checks = Mock()
        self.harness.charm._update_haproxy_connection = Mock()
        self.harness.hooks_disabled()
        self.harness.add_relation("nrpe-external-master", "nrpe")
        self.harness.add_relation("website", "haproxy")
        relation_id = self.harness.add_relation("replicas", "landscape-server")

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.update_relation_data(
                relation_id, "landscape-server", {"leader-ip": "test"}
            )

        self.harness.charm._update_nrpe_checks.assert_called_once()
        self.harness.charm._update_haproxy_connection.assert_not_called()
        mock_update_conf.assert_called_once_with(
            
            {
                    "package-search": {
                        "host": "test",
                    },
                }
        
        )


class TestCreateHAProxyServices(unittest.TestCase):
    """
    Test that the Landscape services receive the correct stanzas in the HAProxy
    configuration.
    """

    def setUp(self):
        with open(HAPROXY_CONFIG_FILE) as f:
            self.haproxy_config = yaml.safe_load(f)
        self.service_ports = {
            "appserver": 8000,
            "pingserver": 8070,
            "message-server": 8090,
            "api": 9080,
            "package-upload": 9100,
            "hostagent-messenger": 50052,
        }
        self.server_options = ["check", "inter 5000", "rise 2", "fall 5", "maxconn 50"]
        self.https_service = self.haproxy_config["https_service"]
        self.http_service = self.haproxy_config["http_service"]
        self.grpc_service = self.haproxy_config["grpc_service"]

    def test_ssl_cert_set(self):
        """
        Uses the provided `ssl_cert` with the HTTPs and gRPC services.
        """

        ssl_cert = "some-ssl-cert"

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert=ssl_cert,
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        self.assertIn(ssl_cert, https["crts"])
        self.assertIn(ssl_cert, grpc["crts"])
        self.assertIsNone(http.get("crts"))

    def test_error_files_set(self):
        """
        Assigns the proivided `error_files` to the http, https, and grpc services.
        """
        error_files = [
            HAProxyErrorFile(http_status=404, content=b64encode(b"Not Found!")),
            HAProxyErrorFile(http_status=405, content=b64encode(b"Not Allowed!")),
            HAProxyErrorFile(http_status=500, content=b64encode(b"Oops, our fault...")),
        ]

        expected = [
            {"http_status": 404, "content": b64encode(b"Not Found!")},
            {"http_status": 405, "content": b64encode(b"Not Allowed!")},
            {"http_status": 500, "content": b64encode(b"Oops, our fault...")},
        ]

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=False,
            error_files=error_files,
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        for service in (http, https, grpc):
            self.assertEqual(expected, service["error_files"])

    def test_http_services(self):
        """
        pingserver and appserver are served over HTTP.
        """
        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )
        backend_stanza = {"backend_name": "landscape-ping", "servers": ANY}

        self.assertIn(backend_stanza, http["backends"])
        self.assertNotIn(backend_stanza, https["backends"])

    def test_https_services(self):
        """
        appserver, api, package upload, and message server are served over HTTPs.
        """
        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip="",
            unit_name="",
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        backend_stanzas = (
            {"backend_name": "landscape-message", "servers": ANY},
            {"backend_name": "landscape-api", "servers": ANY},
            {"backend_name": "landscape-package-upload", "servers": ANY},
            {"backend_name": "landscape-hashid-databases", "servers": ANY},
        )

        for backend_stanza in backend_stanzas:
            self.assertNotIn(backend_stanza, http["backends"])
            self.assertIn(backend_stanza, https["backends"])

    def test_configure_grpc_services(self):
        """
        Each hostagent-messenger receives a
        `landscape-hostagent-messenger-<unit name>-<index> name,
        the server_ip, the correct port, and the server options.

        Counts are based on `worker_count`.

        landscape-hostagent-messenger is set as a server on the gRPC service.
        """

        server_ip = "10.194.61.5"
        unit_name = "0"

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            (
                f"landscape-hostagent-messenger-{unit_name}-0",
                server_ip,
                self.service_ports["hostagent-messenger"],
                self.server_options
                + self.haproxy_config["grpc_service"]["server_options"],
            )
        ]

        self.assertEqual(expected, grpc["servers"])

    def test_configure_appservers(self):
        """
        Each appserver receives a `landscape-appserver-<unit name>-<index> name,
        the server_ip, the correct port, and the server options.

        Counts are based on `worker_count`.

        Appservers are served over HTTP and HTTPs.
        """

        server_ip = "10.194.61.5"
        unit_name = "0"

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=1,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = [
            (
                f"landscape-appserver-{unit_name}-0",
                server_ip,
                self.service_ports["appserver"],
                self.server_options,
            )
        ]

        self.assertEqual(expected, http["servers"])
        self.assertEqual(expected, https["servers"])

    def test_configure_pingservers(self):
        """
        Each pingserver receives a `landscape-pingserver-<unit name>-<index> name,
        the server_ip, the correct port, and the global server options.

        Counts are based on `worker_count`.
        """
        server_ip = "10.194.61.5"
        unit_name = "0"
        worker_counts = 3

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-ping",
            "servers": [
                (
                    f"landscape-pingserver-{unit_name}-{i}",
                    server_ip,
                    self.service_ports["pingserver"] + i,
                    self.server_options,
                )
                for i in range(worker_counts)
            ],
        }

        self.assertIn(expected, http["backends"])
        self.assertNotIn(expected, https["backends"])

    def test_configure_message_servers(self):
        """
        Each message server receives a `landscape-message-server-<unit name>-<index> name,
        the server_ip, the correct port, and the global server options.

        Counts are based on `worker_count`.
        """
        server_ip = "10.194.61.5"
        unit_name = "0"
        worker_counts = 3

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-message",
            "servers": [
                (
                    f"landscape-message-server-{unit_name}-{i}",
                    server_ip,
                    self.service_ports["message-server"] + i,
                    self.server_options,
                )
                for i in range(worker_counts)
            ],
        }

        self.assertIn(expected, https["backends"])
        self.assertNotIn(expected, http["backends"])

    def test_configure_api_servers(self):
        """
        Each API server receives a `landscape-api-<unit name>-<index> name,
        the server_ip, the correct port assigned, the global server options.

        Counts are based on `worker_count`.
        """
        server_ip = "10.194.61.5"
        unit_name = "0"
        worker_counts = 3

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-api",
            "servers": [
                (
                    f"landscape-api-{unit_name}-{i}",
                    server_ip,
                    self.service_ports["api"] + i,
                    self.server_options,
                )
                for i in range(worker_counts)
            ],
        }

        self.assertIn(expected, https["backends"])
        self.assertNotIn(expected, http["backends"])

    def test_configure_package_upload_server(self):
        """
        There is only one package upload server.

        It receives a `landscape-package-upload-<unit name>-0 name, the server_ip,
        the assigned port, and the global server options.

        Package upload only has servers if the unit is the leader. Non-leaders
        declare the backend but do not receive a `servers` configuration.
        """
        server_ip = "10.194.61.5"
        unit_name = "0"
        worker_counts = 3

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-package-upload",
            "servers": [
                (
                    f"landscape-package-upload-{unit_name}-0",
                    server_ip,
                    self.service_ports["package-upload"],
                    self.server_options,
                )
            ],
        }

        self.assertIn(expected, https["backends"])
        self.assertNotIn(expected, http["backends"])

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-package-upload",
            "servers": [],
        }

        self.assertIn(expected, https["backends"])
        self.assertNotIn(expected, http["backends"])

    def test_hashid_databases_backend(self):
        """
        Only the leader receives a server for the `landscape-hashid-databases backend.
        The `landscape-hashids-databases` backend reuses the `appservers` configuration.

        Non-leaders declare the backend but do not have a server.
        """
        server_ip = "10.194.61.5"
        unit_name = "0"
        worker_counts = 3

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=True,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {
            "backend_name": "landscape-hashid-databases",
            "servers": [
                (
                    f"landscape-appserver-{unit_name}-{i}",
                    server_ip,
                    self.service_ports["appserver"] + i,
                    self.server_options,
                )
                for i in range(worker_counts)
            ],
        }

        self.assertIn(expected, https["backends"])
        self.assertNotIn(expected, http["backends"])

        http, https, grpc = _create_haproxy_services(
            http_service=self.http_service,
            https_service=self.https_service,
            grpc_service=self.grpc_service,
            ssl_cert="",
            server_ip=server_ip,
            unit_name=unit_name,
            worker_counts=worker_counts,
            is_leader=False,
            error_files=(),
            service_ports=self.service_ports,
            server_options=self.server_options,
        )

        expected = {"backend_name": "landscape-hashid-databases", "servers": []}

        self.assertIn(expected, https["backends"])
        self.assertNotIn(expected, http["backends"])


# TODO fix from broken commit.
@unittest.skip("Broken in `de29548e2b09c71db3a55f606ab318b5ea25550d`")
class TestBootstrapAccount(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(LandscapeServerCharm)
        self.addCleanup(self.harness.cleanup)

        self.harness.model.get_binding = Mock(
            return_value=Mock(bind_address="123.123.123.123")
        )
        self.harness.add_relation("replicas", "landscape-server")
        self.harness.set_leader()

        pwd_mock = patch("charm.user_exists").start()
        pwd_mock.return_value = Mock(spec_set=struct_passwd, pw_uid=1000)
        grp_mock = patch("charm.group_exists").start()
        grp_mock.return_value = Mock(spec_set=struct_group, gr_gid=1000)

        self.process_mock = patch("subprocess.run").start()
        self.log_mock = patch("charm.logger.error").start()
        self.log_info_mock = patch("charm.logger.info").start()

        env_mock = patch("os.environ").start()
        env_mock.copy.return_value = {}

        self.addCleanup(patch.stopall)

        self.harness.begin()

    @patch("charm.update_service_conf")
    def test_bootstrap_account_doesnt_run_with_missing_configs(self, _):
        self.harness.update_config(
            {"admin_email": "hello@ubuntu.com", "admin_name": "Hello Ubuntu"}
        )
        self.assertIn("password required", self.log_mock.call_args.args[0])
        self.process_mock.assert_not_called()

    @patch("charm.update_service_conf")
    def test_bootstrap_account_password_redacted(self, _):
        self.harness.update_config(
            {
                "admin_email": "hello@ubuntu.com",
                "admin_name": "Hello Ubuntu",
                "admin_password": "secret123",
                "registration_key": "secret123",
                "root_url": "https://www.landscape.com",
            }
        )
        for call in self.log_info_mock.call_args_list:
            self.assertNotIn("secret123", str(call.args))

    @patch("charm.update_service_conf")
    def test_bootstrap_account_doesnt_run_with_missing_rooturl(self, _):
        self.harness.update_config(
            {
                "admin_email": "hello@ubuntu.com",
                "admin_name": "Hello Ubuntu",
                "admin_password": "password",
            }
        )
        self.assertIn("root url", self.log_mock.call_args.args[0])
        self.process_mock.assert_not_called()

    @patch("charm.update_service_conf")
    def test_bootstrap_account_default_root_url_is_used(self, _):
        self.harness.charm._stored.default_root_url = "https://hello.lxd"
        self.harness.update_config(
            {
                "admin_email": "hello@ubuntu.com",
                "admin_name": "Hello Ubuntu",
                "admin_password": "password",
            }
        )
        self.assertIn(
            self.harness.charm._stored.default_root_url,
            self.process_mock.call_args.args[0],
        )

    @patch("charm.update_service_conf")
    def test_bootstrap_account_config_url_over_default(self, _):
        """If config root url and default root url exists, use config url"""
        self.harness.charm._stored.default_root_url = "https://hello.lxd"
        config_root_url = "https://www.landscape.com"
        self.harness.update_config(
            {
                "admin_email": "hello@ubuntu.com",
                "admin_name": "Hello Ubuntu",
                "admin_password": "password",
                "root_url": config_root_url,
            }
        )
        self.assertIn(config_root_url, self.process_mock.call_args.args[0])

    @patch("charm.update_service_conf")
    def test_bootstrap_account_runs_once_with_correct_args(self, _):
        """
        Test that bootstrap account runs with correct args and that it can't
        run again after a successful run
        """
        self.process_mock.return_value.returncode = 0  # Success
        admin_email = "hello@ubuntu.com"
        admin_name = "Hello Ubuntu"
        admin_password = "password"
        root_url = "https://www.landscape.com"
        config = {
            "admin_email": admin_email,
            "admin_name": admin_name,
            "admin_password": admin_password,
            "root_url": root_url,
        }
        self.harness.update_config(config)
        self.assertEqual(
            [
                "/opt/canonical/landscape/bootstrap-account",
                "--admin_email",
                admin_email,
                "--admin_name",
                admin_name,
                "--admin_password",
                admin_password,
                "--root_url",
                root_url,
            ],
            self.process_mock.call_args.args[0],
        )
        self.harness.update_config(config)
        self.process_mock.assert_called_once()

    @patch("charm.update_service_conf")
    def test_bootstrap_account_runs_twice_if_error(self, _):
        """
        If there's an error ensure that bootstrap account runs again and not
        a third time if successful
        """
        self.process_mock.return_value.returncode = 1  # Error here
        admin_email = "hello@ubuntu.com"
        admin_name = "Hello Ubuntu"
        admin_password = "password"
        root_url = "https://www.landscape.com"
        config = {
            "admin_email": admin_email,
            "admin_name": admin_name,
            "admin_password": admin_password,
            "root_url": root_url,
        }
        self.harness.update_config(config)
        self.process_mock.return_value.returncode = 0
        self.harness.update_config(config)
        self.harness.update_config(config)  # Third time
        self.assertEqual(self.process_mock.call_count, 2)

    @patch("charm.update_service_conf")
    def test_bootstrap_account_cannot_run_if_already_bootstrapped(
        self, update_service_conf_mock
    ):
        """
        If user already has created an account outside of the charm,
        then the bootstrap account cannot run again
        """
        self.process_mock.return_value.returncode = 1  # Error here
        self.process_mock.return_value.stderr = "DuplicateAccountError"
        admin_email = "hello@ubuntu.com"
        admin_name = "Hello Ubuntu"
        admin_password = "password"
        root_url = "https://www.landscape.com"
        config = {
            "admin_email": admin_email,
            "admin_name": admin_name,
            "admin_password": admin_password,
            "root_url": root_url,
        }
        self.harness.update_config(config)
        self.harness.update_config(config)
        self.harness.update_config(config)  # Third time
        self.process_mock.assert_called_once()

    @patch("subprocess.run")
    def test_hash_id_databases(self, run_mock):
        event = Mock(spec_set=ActionEvent)

        self.harness.charm._hash_id_databases(event)

        run_mock.assert_called_once_with(
            ["sudo", "-u", "landscape", HASH_ID_DATABASES],
            check=True,
            text=True,
            env=ANY,
        )

    @patch("subprocess.run")
    def test_hash_id_databases_error(self, run_mock):
        event = Mock(spec_set=ActionEvent)
        run_mock.side_effect = CalledProcessError(127, "ouchie")

        self.harness.charm._hash_id_databases(event)

        run_mock.assert_called_once_with(
            ["sudo", "-u", "landscape", HASH_ID_DATABASES],
            check=True,
            text=True,
            env=ANY,
        )
        event.fail.assert_called_once()


class TestGetModifiedEnvVars(unittest.TestCase):
    """Tests for the workaround to patch the PYTHONPATH."""

    def test_removes_juju_python(self):
        """Removes any python paths that contain `juju`"""

        pythonpath = "/var/lib/juju/python3:/usr/lib/python3:/usr/lib/juju/python3.10"

        with patch.dict(os.environ, {"PYTHONPATH": pythonpath}):
            modified = get_modified_env_vars()["PYTHONPATH"]

        self.assertNotIn("/var/lib/juju/python3", modified)
        self.assertNotIn("/usr/lib/juju/python3.10", modified)
        self.assertIn("/usr/lib/python3", modified)
