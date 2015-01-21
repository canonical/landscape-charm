from mock import Mock

from charmhelpers.core.hookenv import ERROR

from lib.install import InstallHook
from lib.tests.helpers import HookTest


class InstallHookTest(HookTest):

    def setUp(self):
        super(InstallHookTest, self).setUp()
        self.fetch = Mock()
        self.hook = InstallHook(
            fetch=self.fetch,
            log=self.logger.log,
            config=self.config.config)

    def test_no_source(self):
        """
        If no APT source is defined the install hook logs an error
        message and exists with code 1.
        """
        self.assertEqual(1, self.hook.run())
        self.assertEqual(
            ("No source config parameter defined", ERROR),
            self.logger.messages[-1])

    def test_add_source(self):
        """
        The install hook adds the configured APT source.
        """
        self.config.data["source"] = "ppa:landscape/14.10"
        self.assertEqual(0, self.hook.run())
        self.fetch.add_source.assert_called_once_with(
            "ppa:landscape/14.10", None)

    def test_install(self):
        """
        The install hook installs the required packages.
        """
        self.config.data["source"] = "ppa:landscape/14.10"
        packages = ["landscape-server"]
        self.fetch.filter_installed_packages.return_value = packages
        self.assertEqual(0, self.hook.run())
        self.fetch.apt_update.assert_called_once_with(fatal=True)
        self.fetch.filter_installed_packages.assert_called_once_with(packages)
        self.fetch.apt_install.assert_called_once_with(packages, fatal=True)
