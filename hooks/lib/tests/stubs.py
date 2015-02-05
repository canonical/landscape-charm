from charmhelpers.core.hookenv import Config


class HookenvStub(object):
    """Provide a testable stub for C{charmhelpers.core.hookenv}."""

    ip = "1.2.3.4"
    hook = "some-hook"
    unit = "landscape-server/0"
    relid = None

    def __init__(self):
        self.messages = []
        self.relations = {}
        self._config = Config()

    def config(self):
        return self._config

    def log(self, message, level=None):
        self.messages.append((message, level))

    def unit_private_ip(self):
        return self.ip

    def local_unit(self):
        return self.unit

    def hook_name(self):
        return self.hook

    def relation_ids(self, reltype=None):
        if reltype:
            return self.relations.get(reltype, {}).keys()
        relation_ids = []
        for reltype in self.relations:
            relation_ids.extend(self.relation_ids(reltype))
        return relation_ids

    def related_units(self, relid=None):
        relid = relid or self.relid
        if relid:
            reltype = relid.split(":")[0]
            return self.relations[reltype][relid].keys()
        units = []
        for reltype in self.relations:
            for relid in self.relations[reltype]:
                units.extend(self.related_units(relid))
        return units

    def relation_get(self, attribute=None, unit=None, rid=None):
        reltype = rid.split(":")[0]
        data = self.relations[reltype][rid][unit]
        if attribute:
            return data.get(attribute)
        return data


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


class ClusterStub(object):
    """Testable stub for C{charmhelpers.contrib.hahelpers.cluster}."""

    leader = True

    def is_elected_leader(self, resource):
        return self.leader


class HostStub(object):
    """Testable stub for C{charmhelpers.core.host}."""

    password = "landscape-sekret"

    def pwgen(self, length=None):
        return self.password
