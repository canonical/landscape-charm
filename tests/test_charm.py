# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import os
import unittest
from grp import struct_group
from io import BytesIO
from pwd import struct_passwd
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from unittest.mock import DEFAULT, Mock, patch, call

import yaml

from ops.charm import ActionEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charms.operator_libs_linux.v0 import apt
from charms.operator_libs_linux.v0.apt import (
    PackageError, PackageNotFoundError)

from charm import (
    DEFAULT_SERVICES, HAPROXY_CONFIG_FILE, LANDSCAPE_PACKAGES, LEADER_SERVICES, LSCTL,
    NRPE_D_DIR, SCHEMA_SCRIPT, LandscapeServerCharm)


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(LandscapeServerCharm)
        self.addCleanup(self.harness.cleanup)

        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        pwd_mock = patch("charm.user_exists").start()
        pwd_mock.return_value = Mock(
            spec_set=struct_passwd, pw_uid=1000)
        grp_mock = patch("charm.group_exists").start()
        grp_mock.return_value = Mock(
            spec_set=struct_group, gr_gid=1000)

        self.addCleanup(patch.stopall)

        self.harness.begin()

    def test_init(self):
        self.assertEqual(self.harness.charm._stored.ready, {
            "db": False,
            "amqp": False,
            "haproxy": False,
        })

    def test_install(self):
        harness = Harness(LandscapeServerCharm)
        relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"})

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            apt=DEFAULT,
            prepend_default_settings=DEFAULT,
            update_service_conf=DEFAULT,
        )
        ppa = harness.model.config.get("landscape_ppa")

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["check_call"].assert_called_once_with(
            ["add-apt-repository", "-y", ppa])
        mocks["apt"].add_package.assert_called_once_with("landscape-server")
        status = harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertEqual(status.message,
                         "Waiting on relations: db, amqp, haproxy")

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
            relation_id, "landscape-server", {"leader-ip": "test"})

        with patches as mocks:
            mocks["apt"].add_package.side_effect = PackageNotFoundError
            harness.begin_with_initial_hooks()

        status = harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to install packages")

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
            relation_id, "landscape-server", {"leader-ip": "test"})

        with patches as mocks:
            mocks["apt"].add_package.side_effect = PackageError("ouch")
            harness.begin_with_initial_hooks()

        status = harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to install packages")

    def test_install_called_process_error(self):
        harness = Harness(LandscapeServerCharm)
        relation_id = harness.add_relation("replicas", "landcape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"})

        with patch("charm.check_call") as mock:
            with patch("charm.update_service_conf"):
                mock.side_effect = CalledProcessError(127, Mock())
                harness.begin_with_initial_hooks()

        status = harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to install packages")

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
            peer_relation_id, "landscape-server", {"leader-ip": "test"})

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["write_ssl_cert"].assert_any_call("MYFANCYCERT=")
        mocks["prepend_default_settings"].assert_called_once_with(
            {"DEPLOYED_FROM": "charm"})

    def test_install_license_file(self):
        harness = Harness(LandscapeServerCharm)
        mock_input = os.path.join(self.tempdir.name, "new_license.txt")

        harness.update_config({"license_file": "file://" + mock_input})
        relation_id = harness.add_relation("replicas", "landcape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"})

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

        mocks["write_license_file"].assert_any_call(
            f"file://{mock_input}", 1000, 1000)

    def test_install_license_file_b64(self):
        harness = Harness(LandscapeServerCharm)
        harness.update_config({"license_file": "VEhJUyBJUyBBIExJQ0VOU0U="})
        relation_id = harness.add_relation("replicas", "landscape-server")
        harness.update_relation_data(
            relation_id, "landscape-server", {"leader-ip": "test"})

        with patch.multiple(
                "charm",
                update_service_conf=DEFAULT,
                write_license_file=DEFAULT,
        ) as mocks:
            harness.begin_with_initial_hooks()

        mocks["write_license_file"].assert_called_once_with(
            "VEhJUyBJUyBBIExJQ0VOU0U=", 1000, 1000)

    def test_update_ready_status_not_running(self):
        self.harness.charm.unit.status = WaitingStatus()

        self.harness.charm._stored.ready.update({
            k: True for k in self.harness.charm._stored.ready.keys()
        })

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

        self.harness.charm._stored.ready.update({
            k: True for k in self.harness.charm._stored.ready.keys()
        })
        self.harness.charm._stored.running = True

        self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, ActiveStatus)
        self.assertEqual(status.message, "Unit is ready")

    def test_update_ready_status_called_process_error(self):
        self.harness.charm.unit.status = WaitingStatus()

        self.harness.charm._stored.ready.update({
            k: True for k in self.harness.charm._stored.ready.keys()
        })

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
                "db_user": "test",
                "db_password": "test_pass",
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

    def test_on_manual_db_config_change(self):
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

        with patch("charm.check_call") as check_call_mock:
            with patch(
                "settings_files.update_service_conf"
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

    def test_on_manual_db_config_change_block_if_error(self):
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
            with patch(
                "settings_files.update_service_conf"
            ) as update_service_conf_mock:
                self.harness.charm._db_relation_changed(mock_event)

        with patch("charm.check_call") as check_call_mock:
            check_call_mock.side_effect = CalledProcessError(127, "ouch")
            self.harness.update_config({"db_host": "hello", "db_port": "world"})

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)


    def test_amqp_relation_joined(self):
        unit = self.harness.charm.unit
        mock_event = Mock()
        mock_event.relation.data = {unit: {}}

        self.harness.charm._amqp_relation_joined(mock_event)

        self.assertEqual(mock_event.relation.data[unit]["username"],
                         "landscape")
        self.assertEqual(mock_event.relation.data[unit]["vhost"], "landscape")

    def test_amqp_relation_changed_no_password(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {}}
        initial_status = self.harness.charm.unit.status

        self.harness.charm._amqp_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertEqual(status, initial_status)
        self.assertFalse(self.harness.charm._stored.ready["amqp"])

    def test_amqp_relation_changed(self):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "hostname": ["test1", "test2"],
                "password": "testpass",
            },
        }

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.charm._amqp_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["amqp"])

        mock_update_conf.assert_called_once_with({
            "broker": {
                "host": "test1,test2",
                "password": "testpass",
            },
        })

    def test_amqp_relation_changed_str_hostname(self):
        """
        Tests proper handling when the event's hostname is a single string.
        """
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "hostname": "test1",
                "password": "testpass",
            },
        }

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.charm._amqp_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["amqp"])

        mock_update_conf.assert_called_once_with({
            "broker": {
                "host": "test1",
                "password": "testpass",
            },
        })

    def test_website_relation_joined_cert_no_key(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {"public-address": "8.8.8.8"}}
        self.harness.disable_hooks()
        self.harness.update_config({"ssl_cert": "NOTDEFAULT", "ssl_key": ""})

        with patch("charm.update_service_conf"):
            self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message,
                         "`ssl_cert` is specified but `ssl_key` is missing")

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
            "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded")

    def test_website_relation_joined_cert_not_DEFAULT_key_not_b64(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {"public-address": "8.8.8.8"}}
        self.harness.disable_hooks()
        self.harness.update_config({
            "ssl_cert": "Tk9UREVGQVVMVA==",
            "ssl_key": "NOTBASE64OHNO",
        })

        with patch("charm.update_service_conf"):
            self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(
            status.message,
            "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded")

    def test_website_relation_joined_cert_not_DEFAULT(self):
        mock_event = Mock()
        mock_event.relation.data = {
            self.harness.charm.unit: {
                "private-address": "192.168.0.1",
            },
            mock_event.unit: {"public-address": "8.8.8.8"},
        }
        self.harness.disable_hooks()
        self.harness.update_config({
            "ssl_cert": "VEhJUyBJUyBBIENFUlQ=",
            "ssl_key": "VEhJUyBJUyBBIEtFWQ==",
        })

        with open(HAPROXY_CONFIG_FILE) as haproxy_config_file:
            haproxy_config = yaml.safe_load(haproxy_config_file)

        haproxy_config["error_files"]["location"] = self.tempdir.name

        for code, filename in haproxy_config["error_files"]["files"].items():
            with open(os.path.join(self.tempdir.name, filename), "w") \
                    as error_file:
                error_file.write("THIS IS ERROR FILE FOR {}\n".format(code))

        mock_haproxy_config = os.path.join(self.tempdir.name,
                                           "my-haproxy-config.yaml")

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
            with open(os.path.join(self.tempdir.name, filename), "w") \
                    as error_file:
                error_file.write("THIS IS ERROR FILE FOR {}\n".format(code))

        mock_haproxy_config = os.path.join(self.tempdir.name,
                                           "my-haproxy-config.yaml")

        with open(mock_haproxy_config, "w") as mock_haproxy_config_file:
            yaml.safe_dump(haproxy_config, mock_haproxy_config_file)

        with patch.multiple(
                "charm", HAPROXY_CONFIG_FILE=mock_haproxy_config,
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

    def test_on_config_changed_no_smtp_change(self):
        self.harness.charm._update_ready_status = Mock()
        self.harness.charm._configure_smtp = Mock()
        self.harness.update_config({"smtp_relay_host": ""})

        self.harness.charm._configure_smtp.assert_not_called()
        self.harness.charm._update_ready_status.assert_called_once()

    def test_on_config_changed_smtp_change(self):
        self.harness.charm._update_ready_status = Mock()
        self.harness.charm._configure_smtp = Mock()
        self.harness.update_config({"smtp_relay_host": "smtp.example.com"})

        self.harness.charm._configure_smtp.assert_called_once_with(
            "smtp.example.com")
        self.harness.charm._update_ready_status.assert_called_once()

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
            self.assertEqual("relayhost = smtp.example.com\n"
                             "othersetting = nada\n",
                             mock_postfix_cf_file.read())

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
            self.assertEqual("relayhost = smtp.example.com\n"
                             "othersetting = nada\n",
                             mock_postfix_cf_file.read())
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test_action_pause(self):
        with patch("charm.check_call") as check_call_mock:
            self.harness.charm._pause(Mock())

        check_call_mock.assert_called_once_with([LSCTL, "stop"])
        self.assertFalse(self.harness.charm._stored.running)

    def test_action_pause_CalledProcessError(self):
        self.harness.charm._stored.running = True
        event = Mock(spec_set=ActionEvent)

        with patch("charm.check_call") as check_call_mock:
            check_call_mock.side_effect = CalledProcessError(127, "ouch")
            self.harness.charm._pause(event)

        check_call_mock.assert_called_once_with([LSCTL, "stop"])
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)
        self.assertTrue(self.harness.charm._stored.running)
        event.fail.assert_called_once()

    def test_action_resume(self):
        self.harness.charm._update_ready_status = Mock()
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            with patch("charm.check_call") as check_call_mock:
                self.harness.charm._resume(event)

        run_mock.assert_called_once_with([LSCTL, "start"], capture_output=True,
                                         text=True)
        check_call_mock.assert_called_once_with([LSCTL, "status"])
        self.harness.charm._update_ready_status.assert_called_once()
        self.assertTrue(self.harness.charm._stored.running)
        event.log.assert_called_once()

    def test_action_resume_CalledProcessError(self):
        self.harness.charm._update_ready_status = Mock()
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            with patch("charm.check_call") as check_call_mock:
                run_mock.return_value = Mock(
                    stdout="Everything is on fire")
                check_call_mock.side_effect = CalledProcessError(127, "uhoh")

                self.harness.charm._resume(event)

        self.assertEqual(2, len(run_mock.mock_calls))
        run_mock.assert_any_call([LSCTL, "start"], capture_output=True,
                                 text=True)
        run_mock.assert_any_call([LSCTL, "stop"])
        check_call_mock.assert_called_once_with([LSCTL, "status"])
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)
        event.log.assert_called_once()
        event.fail.assert_called_once()

    def test_action_upgrade(self):
        event = Mock(spec_set=ActionEvent)
        self.harness.charm._stored.running = False
        prev_status = self.harness.charm.unit.status

        with patch("charm.apt", spec_set=apt) as apt_mock:
            pkg_mock = Mock()
            apt_mock.DebianPackage.from_apt_cache.return_value = pkg_mock
            self.harness.charm._upgrade(event)

        event.log.assert_called_once()
        self.assertEqual(
            apt_mock.DebianPackage.from_apt_cache.call_count,
            len(LANDSCAPE_PACKAGES)
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

        with patch("charm.apt", spec_set=apt) as apt_mock:
            pkg_mock = Mock()
            apt_mock.DebianPackage.from_apt_cache.return_value = pkg_mock
            pkg_mock.ensure.side_effect = PackageNotFoundError("ouch")
            self.harness.charm._upgrade(event)

        event.log.assert_called_once()
        event.fail.assert_called_once()
        apt_mock.DebianPackage.from_apt_cache.assert_called_once_with(
            "landscape-server")
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test_action_migrate_schema(self):
        event = Mock(spec_set=ActionEvent)

        with patch("subprocess.run") as run_mock:
            self.harness.charm._migrate_schema(event)

        event.log.assert_called_once()
        event.fail.assert_not_called()
        run_mock.assert_called_once_with(
            [SCHEMA_SCRIPT], check=True, text=True)

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
            [SCHEMA_SCRIPT], check=True, text=True)
        self.assertIsInstance(self.harness.charm.unit.status, BlockedStatus)

    def test_nrpe_external_master_relation_joined(self):
        mock_event = Mock()
        mock_event.relation.data = {self.harness.charm.unit: {}}
        mock_nrpe_d_dir = os.path.join(self.tempdir.name, "nrpe.d")
        os.mkdir(mock_nrpe_d_dir)

        self.harness.add_relation("replicas", "landscape-server")
        self.harness.model.get_binding = Mock(
            return_value=Mock(bind_address="123.123.123.123"))
        self.harness.charm._update_service_conf = Mock()

        with patch("charm.update_service_conf"):
            self.harness.set_leader()

        with patch("charm.NRPE_D_DIR", new=mock_nrpe_d_dir):
            self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        for service in DEFAULT_SERVICES + LEADER_SERVICES:
            self.assertIn(
                service,
                mock_event.relation.data[self.harness.charm.unit]["monitors"])

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
            return_value=Mock(bind_address="123.123.123.123"))
        self.harness.charm._update_service_conf = Mock()

        with patch("charm.update_service_conf"):
            self.harness.set_leader()

        with patch("os.path.exists") as os_path_exists_mock:
            os_path_exists_mock.return_value = True
            self.harness.charm._nrpe_external_master_relation_joined(mock_event)

        self.assertEqual(len(os_path_exists_mock.mock_calls),
                         len(DEFAULT_SERVICES + LEADER_SERVICES) + 1)

    def test_nrpe_external_master_relation_joined_cfgs_exist_not_leader(self):
        mock_event = Mock()
        unit = self.harness.charm.unit
        mock_event.relation.data = {unit: {}}

        with patch("os.path.exists") as os_path_exists_mock:
            with patch("os.remove") as os_remove_mock:
                os_path_exists_mock.return_value = True
                self.harness.charm._nrpe_external_master_relation_joined(
                    mock_event)

        self.assertEqual(len(os_path_exists_mock.mock_calls),
                         len(DEFAULT_SERVICES + LEADER_SERVICES) + 1)
        self.assertEqual(len(os_remove_mock.mock_calls), len(LEADER_SERVICES))

    def test_nrpe_external_master_relation_joined_cfgs_not_exist_not_leader(
            self):
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
                self.harness.charm._nrpe_external_master_relation_joined(
                    mock_event)

        self.assertEqual(len(os_path_exists_mock.mock_calls),
                         len(DEFAULT_SERVICES + LEADER_SERVICES) + 1)
        self.assertEqual(len(os_remove_mock.mock_calls), 0)

    def test_leader_settings_changed(self):
        """
        Tests that _update_nrpe_checks is called when leader settings
        have changed and an nrpe-external-master relation exists.
        """
        self.harness.charm._update_nrpe_checks = Mock()
        self.harness.hooks_disabled()
        self.harness.add_relation("nrpe-external-master", "nrpe")
        relation_id = self.harness.add_relation("replicas", "landscape-server")
        self.harness.update_relation_data(relation_id, "landscape-server",
                                          {"leader-ip": "test"})

        with patch("charm.update_service_conf") as mock_update_conf:
            self.harness.charm._leader_settings_changed(Mock())

        self.harness.charm._update_nrpe_checks.assert_called_once()
        mock_update_conf.assert_called_once_with({
            "package-search": {
                "host": "test",
            },
        })
