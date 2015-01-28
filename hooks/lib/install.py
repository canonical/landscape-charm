from charmhelpers import fetch

from lib.hook import Hook, HookError

PACKAGES = ("landscape-server",)


class InstallHook(Hook):
    """Execute install hook logic."""

    def __init__(self, fetch=fetch, **kwargs):
        super(InstallHook, self).__init__(**kwargs)
        self._fetch = fetch

    def _run(self):
        self._configure_sources()
        self._install_packages()

    def _configure_sources(self):
        """Configure the extra APT sources to use."""
        config = self._hookenv.config()
        source = config.get("source")
        if not source:
            raise HookError("No source config parameter defined")
        self._fetch.add_source(source, config.get("key"))
        self._fetch.apt_update(fatal=True)

    def _install_packages(self):
        """Install the needed packages."""
        packages = self._fetch.filter_installed_packages(PACKAGES)
        self._fetch.apt_install(packages, fatal=True)
