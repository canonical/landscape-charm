# Copyright 2022 Canonical Ltd
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import os
import unittest
from base64 import b64encode, b64decode
from configparser import ConfigParser
from grp import struct_group
from pwd import struct_passwd
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from unittest.mock import DEFAULT, Mock, patch

import yaml

from ops.charm import RelationChangedEvent
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness

from charms.operator_libs_linux.v0.apt import (
    PackageError, PackageNotFoundError)

from charm import (
    DEBCONF_SET_SELECTIONS, DPKG_RECONFIGURE, HAPROXY_CONFIG_FILE,
    LandscapeServerCharm)

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
        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            add_package=DEFAULT,
        )
        ppa = harness.model.config.get("landscape_ppa")

        with patches as mocks:
            harness.begin_with_initial_hooks()

        mocks["check_call"].assert_called_once_with(
            ["add-apt-repository", "-y", ppa])
        mocks["add_package"].assert_called_once_with("landscape-server")
        status = harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertEqual(status.message,
                         "Waiting on relations: db, amqp, haproxy")

    def test_install_package_not_found_error(self):
        harness = Harness(LandscapeServerCharm)
        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            add_package=DEFAULT,
        )
        ppa = harness.model.config.get("landscape_ppa")

        with patches as mocks:
            mocks["add_package"].side_effect = PackageNotFoundError
            harness.begin_with_initial_hooks()

        status = harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to install packages")

    def test_install_package_error(self):
        harness = Harness(LandscapeServerCharm)

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            add_package=DEFAULT,
        )
        ppa = harness.model.config.get("landscape_ppa")

        with patches as mocks:
            mocks["add_package"].side_effect = PackageError("ouch")
            harness.begin_with_initial_hooks()

        status = harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to install packages")

    def test_install_called_process_error(self):
        harness = Harness(LandscapeServerCharm)

        with patch("charm.check_call") as mock:
            mock.side_effect = CalledProcessError(127, Mock())
            harness.begin_with_initial_hooks()

        status = harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to install packages")

    def test_install_ssl_cert(self):
        harness = Harness(LandscapeServerCharm)
        harness.disable_hooks()
        harness.update_config({"ssl_cert": "MYFANCYCERT="})
        mock_cert_path = os.path.join(self.tempdir.name, "my_cert.crt")

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            add_package=DEFAULT,
            SSL_CERT_PATH=mock_cert_path,
        )
        ppa = harness.model.config.get("landscape_ppa")

        with patches as mocks:
            harness.begin_with_initial_hooks()

        with open(mock_cert_path, "rb") as mock_cert:
            self.assertEqual(mock_cert.read(), b64decode("MYFANCYCERT="))

    def test_install_license_file(self):
        harness = Harness(LandscapeServerCharm)
        mock_license = os.path.join(self.tempdir.name, "my_license.txt")
        mock_input = os.path.join(self.tempdir.name, "new_license.txt")

        with open(mock_input, "w") as mock_input_file:
            mock_input_file.write("THIS IS A LICENSE")

        harness.update_config({"license_file": "file://" + mock_input})

        with patch("charm.LICENSE_FILE", new=mock_license):
            harness.begin_with_initial_hooks()

        with open(mock_license) as mock_license_file:
            mode = 0o777 & os.stat(mock_license_file.fileno()).st_mode
            self.assertEqual(0o640, mode)
            self.assertEqual("THIS IS A LICENSE", mock_license_file.read())

    def test_install_license_file_b64(self):
        harness = Harness(LandscapeServerCharm)
        harness.update_config({"license_file": "VEhJUyBJUyBBIExJQ0VOU0U="})
        mock_license = os.path.join(self.tempdir.name, "my_license.txt")

        with patch("charm.LICENSE_FILE", new=mock_license):
            harness.begin_with_initial_hooks()

        with open(mock_license) as mock_license_file:
            mode = 0o777 & os.stat(mock_license_file.fileno()).st_mode
            self.assertEqual(0o640, mode)
            self.assertEqual("THIS IS A LICENSE", mock_license_file.read())

    def test_write_license_file_URLError(self):
        mock_license = os.path.join(self.tempdir.name, "my_license.txt")
        mock_input = os.path.join(self.tempdir.name, "new_license.txt")

        with patch("charm.LICENSE_FILE", new=mock_license):
            self.harness.charm._write_license_file("file://" + mock_input)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertFalse(os.path.exists(mock_license))

    def test_write_license_file_binascii_Error(self):
        mock_license = os.path.join(self.tempdir.name, "my_license.txt")

        with patch("charm.LICENSE_FILE", new=mock_license):
            self.harness.charm._write_license_file("DECIDEDLYNOTB64")

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertFalse(os.path.exists(mock_license))

    def test_update_ready_status_not_running(self):
        self.harness.charm._stored.ready.update({
            k: True for k in self.harness.charm._stored.ready.keys()
        })
        mock_settings_path = os.path.join(self.tempdir.name,
                                          "my_settings.conf")

        with open(mock_settings_path, "w") as mock_settings_file:
            mock_settings_file.write("RUN_ALL=\"no\"\n")

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            DEFAULT_SETTINGS=mock_settings_path,
        )

        with patches:
            self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, ActiveStatus)
        self.assertEqual(status.message, "Unit is ready")
        self.assertTrue(self.harness.charm._stored.running)

        with open(mock_settings_path) as mock_settings_file:
            self.assertEqual(mock_settings_file.read(), "RUN_ALL=\"yes\"\n")

    def test_update_ready_status_running(self):
        self.harness.charm._stored.ready.update({
            k: True for k in self.harness.charm._stored.ready.keys()
        })
        self.harness.charm._stored.running = True

        self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, ActiveStatus)
        self.assertEqual(status.message, "Unit is ready")

    def test_update_ready_status_called_process_error(self):
        self.harness.charm._stored.ready.update({
            k: True for k in self.harness.charm._stored.ready.keys()
        })
        mock_settings_path = os.path.join(self.tempdir.name, "my_settings")

        with open(mock_settings_path, "w") as mock_settings_file:
            mock_settings_file.write("RUN_ALL=\"no\"\n")

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            DEFAULT_SETTINGS=mock_settings_path,
        )

        with patches as mocks:
            mocks["check_call"].side_effect = CalledProcessError(127, "ouch")
            self.harness.charm._update_ready_status()

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message, "Failed to start services")
        self.assertFalse(self.harness.charm._stored.running)

        with open(mock_settings_path) as mock_settings_file:
            self.assertEqual(mock_settings_file.read(), "RUN_ALL=\"yes\"\n")

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
                "master": True,
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }
        mock_service_conf = os.path.join(self.tempdir.name, "my_service.conf")
        with open(mock_service_conf, "w") as mock_service_conf_file:
            mock_service_conf_file.write("""
[stores]
host = default
password = default
[schema]
store_user = default
store_password = default
            """)

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            SERVICE_CONF=mock_service_conf,
        )

        with patches:
            self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["db"])

        config = ConfigParser()
        config.read(mock_service_conf)
        self.assertEqual(config["stores"]["host"], "1.2.3.4:5678")
        self.assertEqual(config["stores"]["password"], "testpass")
        self.assertEqual(config["schema"]["store_user"], "testuser")
        self.assertEqual(config["schema"]["store_password"], "testpass")

    def test_db_relation_changed_called_process_error(self):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {
                "allowed-units": self.harness.charm.unit.name,
                "master": True,
                "host": "1.2.3.4",
                "port": "5678",
                "user": "testuser",
                "password": "testpass",
            },
        }
        mock_service_conf = os.path.join(self.tempdir.name, "my_service.conf")
        with open(mock_service_conf, "w") as mock_service_conf_file:
            mock_service_conf_file.write("""
[stores]
host = default
password = default
[schema]
store_user = default
store_password = default
""")

        patches = patch.multiple(
            "charm",
            check_call=DEFAULT,
            SERVICE_CONF=mock_service_conf,
        )

        with patches as mocks:
            mocks["check_call"].side_effect = CalledProcessError(127, "ouch")
            self.harness.charm._db_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertFalse(self.harness.charm._stored.ready["db"])

        config = ConfigParser()
        config.read(mock_service_conf)
        self.assertEqual(config["stores"]["host"], "1.2.3.4:5678")
        self.assertEqual(config["stores"]["password"], "testpass")
        self.assertEqual(config["schema"]["store_user"], "testuser")
        self.assertEqual(config["schema"]["store_password"], "testpass")

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
        mock_service_conf = os.path.join(self.tempdir.name, "my_service.conf")
        with open(mock_service_conf, "w") as mock_service_conf_file:
            mock_service_conf_file.write("""
[broker]
host = default
password = default
""")

        with patch("charm.SERVICE_CONF", new=mock_service_conf):
            self.harness.charm._amqp_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["amqp"])

        config = ConfigParser()
        config.read(mock_service_conf)
        self.assertEqual(config["broker"]["host"], "test1,test2")
        self.assertEqual(config["broker"]["password"], "testpass")

    def test_website_relation_joined_cert_no_key(self):
        mock_event = Mock()
        self.harness.disable_hooks()
        self.harness.update_config({"ssl_cert": "NOTDEFAULT", "ssl_key": ""})

        self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(status.message,
                         "`ssl_cert` is specified but `ssl_key` is missing")

    def test_website_relation_joined_cert_not_DEFAULT_not_b64(self):
        mock_event = Mock()
        self.harness.disable_hooks()
        self.harness.update_config({"ssl_cert": "NOTDEFAULT", "ssl_key": "a"})

        self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(
            status.message,
            "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded")

    def test_website_relation_joined_cert_not_DEFAULT_key_not_b64(self):
        mock_event = Mock()
        self.harness.disable_hooks()
        self.harness.update_config({
            "ssl_cert": "Tk9UREVGQVVMVA==",
            "ssl_key": "NOTBASE64OHNO",
        })

        self.harness.charm._website_relation_joined(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, BlockedStatus)
        self.assertEqual(
            status.message,
            "Unable to decode `ssl_cert` or `ssl_key` - must be b64-encoded")

    def test_website_relation_joined_cert_not_DEFAULT(self):
        mock_event = Mock()
        mock_event.relation.data = {self.harness.charm.unit: {
            "private-address": "192.168.0.1",
        }}
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

        with patch("charm.HAPROXY_CONFIG_FILE", mock_haproxy_config):
            self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        status = self.harness.charm.unit.status
        self.assertIn("services", relation_data)
        self.assertIsInstance(status, WaitingStatus)
        self.assertTrue(self.harness.charm._stored.ready["haproxy"])

    def test_website_relation_joined(self):
        mock_event = Mock()
        mock_event.relation.data = {self.harness.charm.unit: {
            "private-address": "192.168.0.1",
        }}

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

        with patch("charm.HAPROXY_CONFIG_FILE", mock_haproxy_config):
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
        mock_ssl_cert = os.path.join(self.tempdir.name, "my_ssl_cert.crt")
        with open(mock_ssl_cert, "w") as mock_ssl_cert_file:
            mock_ssl_cert_file.write("DO NOT PANIC! THIS IS A TEST\n")

        with patch("charm.SSL_CERT_PATH", new=mock_ssl_cert):
            self.harness.charm._website_relation_changed(mock_event)

        self.assertEqual(initial_status, self.harness.charm.unit.status)
        with open(mock_ssl_cert) as mock_ssl_cert_file:
            self.assertEqual("DO NOT PANIC! THIS IS A TEST\n",
                             mock_ssl_cert_file.read())

    def test_website_relation_changed_no_new_cert(self):
        mock_event = Mock()
        mock_event.relation.data = {mock_event.unit: {}}
        initial_status = self.harness.charm.unit.status
        mock_ssl_cert = os.path.join(self.tempdir.name, "my_ssl_cert.crt")
        with open(mock_ssl_cert, "w") as mock_ssl_cert_file:
            mock_ssl_cert_file.write("DO NOT PANIC! THIS IS A TEST\n")

        with patch("charm.SSL_CERT_PATH", new=mock_ssl_cert):
            self.harness.charm._website_relation_changed(mock_event)

        self.assertEqual(initial_status, self.harness.charm.unit.status)
        with open(mock_ssl_cert) as mock_ssl_cert_file:
            self.assertEqual("DO NOT PANIC! THIS IS A TEST\n",
                             mock_ssl_cert_file.read())

    def test_website_relation_changed(self):
        mock_event = Mock()
        mock_event.relation.data = {
            mock_event.unit: {"ssl_cert": "FANCYNEWCERT"},
        }
        mock_ssl_cert = os.path.join(self.tempdir.name, "my_ssl_cert.crt")
        with open(mock_ssl_cert, "w") as mock_ssl_cert_file:
            mock_ssl_cert_file.write("DO NOT PANIC! THIS IS A TEST\n")

        with patch("charm.SSL_CERT_PATH", new=mock_ssl_cert):
            self.harness.charm._website_relation_changed(mock_event)

        status = self.harness.charm.unit.status
        self.assertIsInstance(status, WaitingStatus)
        with open(mock_ssl_cert, "rb") as mock_ssl_cert_file:
            self.assertEqual(b"FANCYNEWCERT",
                             b64encode(mock_ssl_cert_file.read()))

    def test_default_settings_passthrough_lines(self):
        mock_default_settings = os.path.join(self.tempdir.name, "my_settings")

        with open(mock_default_settings, "w") as mock_default_settings_file:
            mock_default_settings_file.write(
                "DONOTTOUCH=\"THIS\"\nTOUCHTHIS=\"PLEASE\"\n")

        with patch("charm.DEFAULT_SETTINGS", new=mock_default_settings):
            self.harness.charm._update_default_settings(
                "TOUCHTHIS", "THANKYOU")

        with open(mock_default_settings) as mock_default_settings_file:
            self.assertEqual(
                "DONOTTOUCH=\"THIS\"\nTOUCHTHIS=\"THANKYOU\"\n",
                mock_default_settings_file.read())

    def test_on_config_changed_no_smtp_change(self):
        self.harness.charm._configure_smtp = Mock()
        self.harness.update_config({"smtp_relay_host": ""})

        self.harness.charm._configure_smtp.assert_not_called()

    def test_on_config_changed_smtp_change(self):
        self.harness.charm._configure_smtp = Mock()
        self.harness.update_config({"smtp_relay_host": "smtp.example.com"})

        self.harness.charm._configure_smtp.assert_called_once_with(
            "smtp.example.com")

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
