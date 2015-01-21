from charmhelpers.core.hookenv import cached, Config


class HookenvStub(object):
    """Provide a testable stub for C{charmhelpers.core.hookenv}."""

    def __init__(self):
        self.messages = []

    @cached
    def config(self):
        return Config()

    def log(self, message, level=None):
        self.messages.append((message, level))


class FetchStub(object):
    """Provide a testable stub for C{charmhelpers.fetch}."""

    def __init__(self):
        self.sources = []
        self.updates = []
        self.filtered = []
        self.installed = []

    def add_source(self, source, key=None):
        self.sources.append((source, key))

    def apt_update(self, fatal=False):
        self.updates.append(fatal)

    def filter_installed_packages(self, packages):
        self.filtered.append(packages)
        return packages

    def apt_install(self, packages, fatal=False):
        self.installed.append((packages, fatal))
