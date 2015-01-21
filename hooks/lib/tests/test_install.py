from charmhelpers.core.hookenv import ERROR

from lib.install import InstallHook, PACKAGES
from lib.tests.stubs import FetchStub
from lib.tests.hook import HookTest


class InstallHookTest(HookTest):

    def setUp(self):
        super(InstallHookTest, self).setUp()
        self.fetch = FetchStub()
        self.hook = InstallHook(
            fetch=self.fetch,
            hookenv=self.hookenv)

    def test_no_source(self):
        """
        If no APT source is defined the install hook logs an error
        message and exists with code 1.
        """
        self.assertEqual(1, self.hook())
        self.assertEqual(
            ("No source config parameter defined", ERROR),
            self.hookenv.messages[-1])

    def test_add_source(self):
        """
        The install hook adds the configured APT source and refreshes it.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.assertEqual(0, self.hook())
        self.assertEqual([("ppa:landscape/14.10", None)], self.fetch.sources)
        self.assertEqual([True], self.fetch.updates)

    def test_packages(self):
        """
        The C{PACKAGES} tuple holds the packages expected to get installed.
        """
        self.assertEqual(("landscape-server",), PACKAGES)

    def test_install(self):
        """
        The install hook installs the required packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.assertEqual(0, self.hook())
        self.assertEqual([PACKAGES], self.fetch.filtered)
        self.assertEqual([(PACKAGES, True)], self.fetch.installed)
