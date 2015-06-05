import os
import subprocess

from fixtures import TempDir

from lib.apt import (
    Apt, AptError, PACKAGES, DEFAULT_INSTALL_OPTIONS, SAMPLE_HASHIDS_PPA,
    SAMPLE_HASHIDS_KEY)
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.tests.helpers import HookenvTest
from lib.tests.rootdir import RootDir


class AptTest(HookenvTest):

    def setUp(self):
        super(AptTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.root_dir = self.useFixture(RootDir())
        self.paths = self.root_dir.paths
        self.subprocess.add_fake_executable("add-apt-repository")
        self.subprocess.add_fake_executable(
            "/usr/lib/pbuilder/pbuilder-satisfydepends")
        self.apt = Apt(
            hookenv=self.hookenv, fetch=self.fetch, subprocess=self.subprocess,
            paths=self.paths)

    def _create_local_tarball(self, name, version):
        """Create a local minimal source package tarball that can be built.

        It will be put in the charm directory.
        """
        build_dir = self.useFixture(TempDir())
        package_name = "{}-{}".format(name, version)
        package_dir = build_dir.join(package_name)
        os.mkdir(package_dir)
        subprocess.check_output(["dh_make", "-n", "-i", "-y"], cwd=package_dir)
        tarball = os.path.join(
            self.hookenv.charm_dir(), "{}_{}.tar.gz".format(name, version))
        subprocess.check_output(
            ["tar", "zcvf", tarball, package_name], cwd=build_dir.path)

    def test_no_source(self):
        """
        If no APT source is defined, we fail with an AptError.
        """
        with self.assertRaises(AptError) as error:
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

    def test_set_sources_sample_hashids(self):
        """
        The C{set_sources} method adds the sample hashids PPA if a
        file named 'use-sample-hashids' is found.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        flag_file = os.path.join(
            self.hookenv.charm_dir(), "use-sample-hashids")
        with open(flag_file, "w") as fd:
            fd.write("")
        self.apt.set_sources()
        self.assertEqual(
            [("ppa:landscape/14.10", None),
             (SAMPLE_HASHIDS_PPA, SAMPLE_HASHIDS_KEY)],
            self.fetch.sources)
        self.assertEqual([True], self.fetch.updates)

    def test_local_tarball(self):
        """
        If a Landscape tarball is found, the C{set_sources} method builds local
        repository with the relevant deb packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self._create_local_tarball("landscape-server", "1.2.3")
        self.apt.set_sources()

        build_dir = os.path.join(self.hookenv.charm_dir(), "build", "package")
        self.assertTrue(os.path.exists(os.path.join(
            build_dir, "landscape-server_1.2.3_all.deb")))

        self.assertIn(
            (["/usr/lib/pbuilder/pbuilder-satisfydepends"],
             {"cwd": build_dir}),
            self.subprocess.calls)

        self.assertEqual(
            [("ppa:landscape/14.10", None),
             ("deb file://%s/build/package/ ./" % self.hookenv.charm_dir(),
              None)],
            self.fetch.sources)
        # XXX: We should check that the generated repository is valid.

    def test_local_tarball_not_new(self):
        """
        If the landscape tarball hasn't changed, it won't be built.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self._create_local_tarball("landscape-server", "1.2.3")
        self.apt.set_sources()

        # Reset the recorded sources and subprocess calls and run again
        self.subprocess.calls[:] = []
        self.fetch.sources[:] = []
        self.apt.set_sources()
        self.assertEqual([], self.subprocess.calls)
        self.assertEqual([("ppa:landscape/14.10", None)], self.fetch.sources)

    def test_wb_get_local_epoch_with_epoch(self):
        """
        If an installed landscape-server package has an epoch,
        _get_local_epoch() returns the installed epoch + 1.
        """
        self.subprocess.add_fake_executable(
            "dpkg-query", lambda *args, **kwargs: (0, "1:1.2.3", ""))
        self.assertEqual(2, self.apt._get_local_epoch())
        self.assertIn(
            (["dpkg-query", "-f", "${version}", "-W", "landscape-server"], {}),
            self.subprocess.calls)

    def test_wb_get_local_epoch_with_no_epoch(self):
        """
        If an installed landscape-server package has no epoch,
        _get_local_epoch() returns the 1000.
        """
        self.subprocess.add_fake_executable(
            "dpkg-query", lambda *args, **kwargs: (0, "1.2.3", ""))
        self.assertEqual(1000, self.apt._get_local_epoch())
        self.assertIn(
            (["dpkg-query", "-f", "${version}", "-W", "landscape-server"], {}),
            self.subprocess.calls)

    def test_wb_get_local_epoch_not_installed(self):
        """
        If no landscape-server package is installed _get_local_epoch()
        returns the 1000.
        """
        self.subprocess.add_fake_executable(
            "dpkg-query", lambda *args, **kwargs: (1, "", "no such package"))
        self.assertEqual(1000, self.apt._get_local_epoch())
        self.assertIn(
            (["dpkg-query", "-f", "${version}", "-W", "landscape-server"], {}),
            self.subprocess.calls)

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

    def test_install_sample_hashids(self):
        """
        If a file named 'use-sample-hashids' is found the install() method
        replaces the real hash-id-databases config file with the sample one.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        charm_dir = self.hookenv.charm_dir()
        config_dir = self.paths.config_dir()
        flag_file = os.path.join(charm_dir, "use-sample-hashids")
        real = os.path.join(config_dir, "hash-id-databases.conf")
        sample = os.path.join(config_dir, "hash-id-databases-sample.conf")
        with open(flag_file, "w") as fd:
            fd.write("")
        with open(real, "w") as fd:
            fd.write("real")
        with open(sample, "w") as fd:
            fd.write("sample")
        self.apt.install_packages()

        with open(real + ".orig") as fd:
            self.assertEqual("real", fd.read())

        with open(real) as fd:
            self.assertEqual("sample", fd.read())

    def test_install_sample_hashids_idempotent(self):
        """
        The real hash-id-databases configuration file is not renamed again
        if was already.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        charm_dir = self.hookenv.charm_dir()
        config_dir = self.paths.config_dir()
        flag_file = os.path.join(charm_dir, "use-sample-hashids")
        real = os.path.join(config_dir, "hash-id-databases.conf")
        sample = os.path.join(config_dir, "hash-id-databases-sample.conf")
        with open(flag_file, "w") as fd:
            fd.write("")
        with open(real, "w") as fd:
            fd.write("real")
        with open(sample, "w") as fd:
            fd.write("sample")
        self.apt.install_packages()
        self.apt.install_packages()

        with open(real + ".orig") as fd:
            self.assertEqual("real", fd.read())

        with open(real) as fd:
            self.assertEqual("sample", fd.read())
