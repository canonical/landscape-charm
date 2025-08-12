import os
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import DEFAULT, Mock, patch

from ops.testing import Harness
import yaml

from charm import (
    HAPROXY_CONFIG_FILE,
    LandscapeServerCharm,
)


class TestHAProxyConfigurations(unittest.TestCase):
    """
    Test that the output into the HAProxy relation does not change between commits
    for various configuration parameters.
    """

    GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "haproxy_golden_files")

    def setUp(self):

        self.harness = Harness(LandscapeServerCharm)
        self.addCleanup(self.harness.cleanup)

        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        self.harness.begin()

    def assertMatchesGolden(self, name: str, actual: str):
        """
        Compare `actual` against the golden file contents.
        If the golden file doesn't exist, create it.

        `actual` is a YAML string for the "services" configuration for HAProxy.
        """
        golden_path = os.path.join(self.GOLDEN_DIR, name)
        os.makedirs(self.GOLDEN_DIR, exist_ok=True)

        if not os.path.exists(golden_path):
            # Write new golden master
            with open(golden_path, "w", encoding="utf-8") as f:
                f.write(actual)
            self.skipTest(f"Golden file {name} created. Verify and re-run tests.")
        else:
            # Compare with existing
            with open(golden_path, "r", encoding="utf-8") as f:
                expected = yaml.safe_load(f.read())
                serialized = yaml.safe_load(actual)
            self.assertEqual(serialized, expected, f"Mismatch in golden file: {name}")

    def _make_fake_haproxy_configuration_file(self):
        with open(HAPROXY_CONFIG_FILE) as haproxy_config_file:
            haproxy_config = yaml.safe_load(haproxy_config_file)

        haproxy_config["error_files"]["location"] = self.tempdir.name

        for code, filename in haproxy_config["error_files"]["files"].items():
            with open(os.path.join(self.tempdir.name, filename), "w") as error_file:
                error_file.write("THIS IS ERROR FILE FOR {}\n".format(code))

        mock_haproxy_config = os.path.join(self.tempdir.name, "my-haproxy-config.yaml")

        with open(mock_haproxy_config, "w") as mock_haproxy_config_file:
            yaml.safe_dump(haproxy_config, mock_haproxy_config_file)

        return mock_haproxy_config

    def test_ssl_cert_and_key(self):

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

        mock_haproxy_config = self._make_fake_haproxy_configuration_file()

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        self.assertMatchesGolden("test_ssl_cert_and_key", relation_data["services"])

    def test_default_ssl_cert_and_key(self):
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
                "ssl_cert": "DEFAULT",
                "ssl_key": "",
            }
        )

        mock_haproxy_config = self._make_fake_haproxy_configuration_file()

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        self.assertMatchesGolden(
            "test_default_ssl_cert_and_key", relation_data["services"]
        )

    def test_worker_counts(self):
        mock_event = Mock()
        mock_event.relation.data = {
            self.harness.charm.unit: {
                "private-address": "192.168.0.1",
            },
            mock_event.unit: {"public-address": "8.8.8.8"},
        }
        self.harness.disable_hooks()
        self.harness.update_config({"worker_counts": 3})

        mock_haproxy_config = self._make_fake_haproxy_configuration_file()

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        self.assertMatchesGolden("test_worker_counts", relation_data["services"])

    def test_non_leader(self):
        mock_event = Mock()
        mock_event.relation.data = {
            self.harness.charm.unit: {
                "private-address": "192.168.0.1",
            },
            mock_event.unit: {"public-address": "8.8.8.8"},
        }
        self.harness.disable_hooks()
        self.harness.update_config({"worker_counts": 1})

        mock_haproxy_config = self._make_fake_haproxy_configuration_file()

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            with patch.object(self.harness.charm.unit, "is_leader", return_value=False):
                self.assertFalse(self.harness.charm.unit.is_leader())
                self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        self.assertMatchesGolden("test_non_leader", relation_data["services"])

    def test_leader(self):
        mock_event = Mock()
        mock_event.relation.data = {
            self.harness.charm.unit: {
                "private-address": "192.168.0.1",
            },
            mock_event.unit: {"public-address": "8.8.8.8"},
        }
        self.harness.disable_hooks()
        self.harness.update_config({"worker_counts": 1})

        mock_haproxy_config = self._make_fake_haproxy_configuration_file()

        with patch.multiple(
            "charm",
            HAPROXY_CONFIG_FILE=mock_haproxy_config,
            update_service_conf=DEFAULT,
        ):
            with patch.object(self.harness.charm.unit, "is_leader", return_value=True):
                self.assertTrue(self.harness.charm.unit.is_leader())
                self.harness.charm._website_relation_joined(mock_event)

        relation_data = mock_event.relation.data[self.harness.charm.unit]
        self.assertMatchesGolden("test_leader", relation_data["services"])
