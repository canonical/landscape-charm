import glob
import hashlib
import os
import re
import shutil
import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv

from lib.error import CharmError
from lib.paths import default_paths

LANDSCAPE_PACKAGES = ("landscape-server", "landscape-hashids")
INSTALL_PACKAGES = LANDSCAPE_PACKAGES + ("python-psutil",)
PACKAGES_DEV = ("dpkg-dev", "pbuilder")
TARBALL = "landscape-server_*.tar.gz"

# XXX Eventually we'll want to use a dedicated PPA, populated by Jenkins.
SAMPLE_HASHIDS_PPA = "ppa:landscape/fake-kernel"
SAMPLE_HASHIDS_KEY = "4652B4E6"

# XXX Default options taken from charmhelpers, there's no way to just
#     extend them.
DEFAULT_INSTALL_OPTIONS = ("--option=Dpkg::Options::=--force-confold",)

BASE_EPOCH = 1000
# Shell commands to build the debs and publish them in a local repository
BUILD_LOCAL_ARCHIVE = """
dch -v {}:$(dpkg-parsechangelog|grep ^Version:|cut -d ' ' -f 2) \
    development --distribution $(lsb_release -cs) &&
dpkg-buildpackage -us -uc &&
mv ../*.deb . &&
dpkg-scanpackages -m . /dev/null > Packages &&
cat Packages | bzip2 -9 > Packages.bz2 &&
cat Packages | gzip -9 > Packages.gz &&
dpkg-scansources . > Sources &&
cat Sources | bzip2 -9 > Sources.bz2 &&
cat Sources | gzip -9 > Sources.gz &&
apt-ftparchive release . > Release
"""


class AptNoSourceConfigError(CharmError):
    """Raise when there is no source config provided."""

    def __init__(self):
        message = "No source config parameter defined"
        super(AptNoSourceConfigError, self).__init__(message)


class AptSourceAndKeyDontMatch(CharmError):
    """Raise the provided 'source' and 'key' config values don't match."""

    def __init__(self):
        message = "The 'source' and 'key' lists have different lengths"
        super(AptSourceAndKeyDontMatch, self).__init__(message)


class Apt(object):
    """Perform APT-related tasks as setting sources and installing packages.

    This is a thin facade around C{charmhelpers.fetch}, offering some
    additional features, like building Landscape packages from a local
    tarball.
    """

    def __init__(self, hookenv=hookenv, fetch=fetch, subprocess=subprocess,
                 paths=default_paths):
        self._hookenv = hookenv
        self._fetch = fetch
        self._subprocess = subprocess
        self._paths = paths

    def set_sources(self, force_update=False):
        """Configure the extra APT sources to use."""
        needs_update = force_update
        if self._set_remote_source():
            needs_update = True
        if self._set_local_source():
            needs_update = True
        if needs_update:
            self._fetch.apt_update(fatal=True)

    def install_packages(self, options=None):
        """Install the needed packages."""
        if options is None:
            options = list(DEFAULT_INSTALL_OPTIONS)
        if self._get_local_tarball() is not None:
            # We don't sign the locally built repository, so we need to tell
            # apt-get that we don't care.
            options.append("--allow-unauthenticated")
        self._fetch.apt_install(INSTALL_PACKAGES, options=options, fatal=True)

        if self._use_sample_hashids():
            config_dir = self._paths.config_dir()
            real = os.path.join(config_dir, "hash-id-databases.conf")
            sample = os.path.join(config_dir, "hash-id-databases-sample.conf")
            if not os.path.exists(real + ".orig"):
                os.rename(real, real + ".orig")
                shutil.copy(sample, real)

    def hold_packages(self):
        """
        Mark the landscape package and the packages depending on it for "hold".
        """
        packages = list(LANDSCAPE_PACKAGES)
        self._subprocess.check_call(["apt-mark", "hold"] + packages)

    def unhold_packages(self):
        """
        Unmark the landscape package and the packages depending on it for
        "hold". This is the opposite of hold_packages, and is used during
        upgrades.

        Theoretically you would be able to ignore the lock by passing
        --ignore-hold to apt, but unfortunately it seems not to work in
        non-interactive mode (LP: #1226168)
        """
        packages = list(LANDSCAPE_PACKAGES)
        self._subprocess.check_call(["apt-mark", "unhold"] + packages)

    def _set_remote_source(self):
        """Set the remote APT repository to use, if new or changed."""
        config = self._hookenv.config()
        source = config.get("source")
        if not source:
            raise AptNoSourceConfigError()

        # The source can be i.e. "15.04" or "14.10" for public PPAs, and we'll
        # do the conversion automatically for UX
        repositories = self._parse_source(source)

        # For each repository, check if we're setting the repository for the
        # first time, or replacing an existing value. In the latter case we'll
        # no-op if the value is the same or take care to remove it from
        # sources.list if it's not in the new list.
        previous_source = config.previous("source")
        if previous_source is not None:
            previous_repositories = self._parse_source(previous_source)
            if set(previous_repositories) == set(repositories):
                return False
            for repository in set(previous_repositories) - set(repositories):
                self._subprocess.check_call(
                    ["add-apt-repository", "--remove", "--yes", repository])

        if not config.get("key"):
            keys = [None] * len(repositories)
        else:
            keys = self._parse_key(config.get("key"))

        if len(repositories) != len(keys):
            raise AptSourceAndKeyDontMatch()

        for repository, key in zip(repositories, keys):
            self._fetch.add_source(repository, key)

        if self._use_sample_hashids():
            self._fetch.add_source(SAMPLE_HASHIDS_PPA, SAMPLE_HASHIDS_KEY)

        return True

    def _parse_source(self, source):
        """Parse the string value of the 'source' config entry.

        @param: A comma-separated string of the desired repositories.
        @return: A list of actual repositories (shorcuts are converted).
        """
        repositories = []
        for repository in source.split(","):
            repository = self._convert_repository_shortcut(repository.strip())
            repositories.append(repository)
        return repositories

    def _parse_key(self, key):
        """Parse the string value of the 'key' config entry.

        @param: A comma-separated string of the key IDs for the desired
            repositories. The special value 'null' means no key is needed
            for the given repository.
        @return: A list of actual keys ('null' is converted to None).
        """
        keys = []
        for entry in key.split(","):
            entry = entry.strip()
            if entry == "null":
                entry = None
            keys.append(entry)
        return keys

    def _convert_repository_shortcut(self, repository):
        """Convert a PPA shortcut like '15.11' to 'ppa:landscape/15.11'.

        For a nicer UX, we accept shortcuts as '15.11'. This method will
        resolve them to the actual PPA value.

        @param repository: A string repository to convert.
        @return: The converted version if the input was shortcut, otherwise
             the same string as the input.
        """
        if re.match("[0-9]{2}\.[0-9]{2}$", repository):
            repository = "ppa:landscape/%s" % repository
        return repository

    def _set_local_source(self):
        """Set the local APT repository for the Landscape tarball, if any."""
        tarball = self._get_local_tarball()
        if tarball is None:
            return False

        if not self._is_tarball_new(tarball):
            return False

        packages = self._fetch.filter_installed_packages(PACKAGES_DEV)
        self._fetch.apt_install(packages, fatal=True)

        build_dir = os.path.join(self._hookenv.charm_dir(), "build", "package")
        shutil.rmtree(build_dir, ignore_errors=True)
        os.makedirs(build_dir)

        epoch = self._get_local_epoch()
        self._subprocess.check_call(
            ["tar", "--strip=1", "-xf", tarball], cwd=build_dir)
        self._subprocess.check_call(
            ["/usr/lib/pbuilder/pbuilder-satisfydepends"], cwd=build_dir)
        self._subprocess.check_call(
            BUILD_LOCAL_ARCHIVE.format(epoch), shell=True, cwd=build_dir)

        self._fetch.add_source("deb file://%s/ ./" % build_dir)

        return True

    def _get_local_epoch(self):
        """Get the epoch to use for the locally built package.

        If landscape-server is installed, an epoch greater than the one
        installed is chosen. If no landscape-server package is
        installed, an epoch of 1000 is chosen to ensure it's greater
        than any PPA version.
        """
        try:
            version = self._subprocess.check_output(
                ["dpkg-query", "-f", "${version}", "-W", "landscape-server"])
        except subprocess.CalledProcessError:
            version = ""
        if ":" not in version:
            return BASE_EPOCH
        epoch = int(version.split(":", 1)[0])
        return epoch + 1

    def _get_local_tarball(self):
        """Return the local Landscape tarball if any, C{None} otherwise."""
        matches = glob.glob(os.path.join(self._hookenv.charm_dir(), TARBALL))
        return matches[0] if matches else None

    def _is_tarball_new(self, tarball):
        """Check if this is a new tarball and we need to build it."""
        with open(tarball, "r") as fd:
            digest = hashlib.md5(fd.read()).hexdigest()

        md5sum = tarball + ".md5sum"
        if os.path.exists(md5sum):
            with open(md5sum, "r") as fd:
                if fd.read() == digest:
                    # The checksum matches, so it's not a new tarball
                    return False

        # Update the md5sum file, since this is a new tarball.
        with open(md5sum, "w") as fd:
            fd.write(digest)

        return True

    def _use_sample_hashids(self):
        """Whether to use sample hashids instead of the real ones.

        This method will check for a 'use-sample-hashids' file in the charm
        directory and return True if it finds one.
        """
        charm_dir = self._hookenv.charm_dir()
        return os.path.exists(os.path.join(charm_dir, "use-sample-hashids"))
