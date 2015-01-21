from charmhelpers import fetch
from charmhelpers.core.hookenv import ERROR

from lib.hook import Hook


class InstallHook(Hook):

    def __init__(self, fetch=fetch, **kwargs):
        super(InstallHook, self).__init__(**kwargs)
        self.fetch = fetch

    def run(self):
        self.log("Installing landscape-server")
        config = self.config()
        source = config.get("source")
        if not source:
            self.log("No source config parameter defined", level=ERROR)
            return 1
        self.fetch.add_source(source, config.get("key"))
        self.fetch.apt_update(fatal=True)
        packages = self.fetch.filter_installed_packages(["landscape-server"])
        self.fetch.apt_install(packages, fatal=True)
        return 0
