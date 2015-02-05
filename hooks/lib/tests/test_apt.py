import os

from lib.apt import Apt, PACKAGES, BUILD_LOCAL_ARCHIVE, DEFAULT_INSTALL_OPTIONS
from lib.hook import HookError
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.tests.helpers import HookenvTest


class AptTest(HookenvTest):

    def setUp(self):
        super(AptTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.apt = Apt(
            hookenv=self.hookenv, fetch=self.fetch, subprocess=self.subprocess)

    def test_no_source(self):
        """
        If no APT source is defined, we fail with a L{HookError}.
        """
        with self.assertRaises(HookError) as error:
            self.apt.set_sources()
        self.assertEqual(
            "No source config parameter defined", str(error.exception))

    def test_set_sources(self):
        """
        The C{set_sources} method adds the configured APT source and
        refreshes it.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.apt.set_sources()
        self.assertEqual([("ppa:landscape/14.10", None)], self.fetch.sources)
        self.assertEqual([True], self.fetch.updates)

    def test_set_sources_not_changed(self):
        """
        The C{set_sources} method is a no-op if the source config hasn't
        changed.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config.load_previous()
        self.apt.set_sources()
        self.assertEqual([], self.fetch.sources)
        self.assertEqual([], self.fetch.updates)

    def test_set_sources_replace(self):
        """
        The C{set_sources} method removes any previous source before setting
        the new one.
        """
        config = self.hookenv.config()
        config["source"] = "ppa:landscape/14.10"
        config.save()
        config.load_previous()
        config["source"] = "ppa:landscape/15.01"
        self.apt.set_sources()
        self.assertEqual(
            ["add-apt-repository", "--remove", "--yes", "ppa:landscape/14.10"],
            self.subprocess.calls[0][0])
        self.assertEqual([("ppa:landscape/15.01", None)], self.fetch.sources)
        self.assertEqual([True], self.fetch.updates)

    def test_local_tarball(self):
        """
        If a Landscape tarball is found, the C{set_sources} method builds local
        repository with the relevant deb packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        tarball = os.path.join(
            self.hookenv.charm_dir(), "landscape-server_1.2.3.tar.gz")
        with open(tarball, "w") as fd:
            fd.write("")
        self.apt.set_sources()

        self.assertEqual(
            [(["tar", "--strip=1", "-xf", tarball], {}),
             (BUILD_LOCAL_ARCHIVE, {"shell": True})],
            self.subprocess.calls)

        self.assertEqual(
            [("ppa:landscape/14.10", None),
             ("deb file://%s/build/ ./" % self.hookenv.charm_dir(), None)],
            self.fetch.sources)

    def test_local_tarball_not_new(self):
        """
        If the landscape tarball hasn't changed, it won't be built.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        tarball = os.path.join(
            self.hookenv.charm_dir(), "landscape-server_1.2.3.tar.gz")
        with open(tarball, "w") as fd:
            fd.write("data")
        self.apt.set_sources()

        # Reset the recorded subprocess calls and run again
        self.subprocess.calls[:] = []
        self.apt.set_sources()
        self.assertEqual([], self.subprocess.calls)

    def test_packages(self):
        """
        The C{PACKAGES} tuple holds the packages expected to get installed.
        """
        self.assertEqual(("landscape-server",), PACKAGES)

    def test_install(self):
        """
        The C{install_packages} method installs the required packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.apt.install_packages()
        self.assertEqual([PACKAGES], self.fetch.filtered)
        options = list(DEFAULT_INSTALL_OPTIONS)
        self.assertEqual([(PACKAGES, options, True)], self.fetch.installed)

    def test_install_with_local_tarball(self):
        """
        The C{install_packages} method allows unauthenticated packages if we
        have a locally built repository.
        """
        tarball = os.path.join(
            self.hookenv.charm_dir(), "landscape-server_1.2.3.tar.gz")
        with open(tarball, "w") as fd:
            fd.write("")
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.apt.install_packages()
        options = list(DEFAULT_INSTALL_OPTIONS) + ["--allow-unauthenticated"]
        self.assertEqual([(PACKAGES, options, True)], self.fetch.installed)
