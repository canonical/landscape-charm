from unittest import TestCase

from lib.paths import Paths, default_paths


class PathsTest(TestCase):

    def test_service_conf_default(self):
        """
        The service_conf() method returns the path to service.conf.
        """
        self.assertEqual(
            "/etc/landscape/service.conf", default_paths.service_conf())

    def test_service_conf_with_root_dir(self):
        """
        The service_conf() method returns the path to service.conf,
        prepended with the root_dir if given.
        """
        paths = Paths(root_dir="/foo")
        self.assertEqual(
            "/foo/etc/landscape/service.conf", paths.service_conf())

    def test_default_file(self):
        """
        The service_conf() method returns the path to service.conf.
        """
        self.assertEqual(
            "/etc/default/landscape-server", default_paths.default_file())

    def test_config_link(self):
        """
        The config_link() method returns the path to the symlink used for
        non-standalone configurations.
        """
        self.assertEqual(
            "/opt/canonical/landscape/configs/edge",
            default_paths.config_link("edge"))
