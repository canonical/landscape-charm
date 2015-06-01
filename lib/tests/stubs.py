import subprocess

from charmhelpers.core.hookenv import Config


class HookenvStub(object):
    """Provide a testable stub for C{charmhelpers.core.hookenv}."""

    ip = "1.2.3.4"
    hook = "some-hook"
    unit = "landscape-server/0"
    relid = None

    def __init__(self, charm_dir):
        self.messages = []
        self.relations = {}
        self._config = Config()
        self._charm_dir = charm_dir

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

    def relation_set(self, rid=None, relation_settings=None, **kwargs):
        self.relations[rid] = relation_settings

    def charm_dir(self):
        return self._charm_dir


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

    def apt_install(self, packages, options=None, fatal=False):
        self.installed.append((packages, options, fatal))


class ClusterStub(object):
    """Testable stub for C{charmhelpers.contrib.hahelpers.cluster}."""

    leader = True

    def is_elected_leader(self, resource):
        return self.leader


class HostStub(object):
    """Testable stub for C{charmhelpers.core.host}."""

    password = "landscape-sekret"
    secret_token = "landscape-token"
    write_file_calls = []

    def __init__(self):
        self.calls = []

    def pwgen(self, length=None):
        if length == 172:
            return self.secret_token
        else:
            return self.password

    def write_file(self, *args, **kwargs):
        self.calls.append(("write_file", args, kwargs))


class SubprocessStub(object):
    """Testable stub for C{subprocess}.

    By default it will pass through the calls to the real subprocess
    module, but it's possible to provide fake output results by calling
    add_fake_call().

    @ivar calls: A list of all calls that have been made.
    """

    def __init__(self):
        self.calls = []
        self._fake_executables = {}

    def add_fake_executable(self, executable, handler=None):
        """Register fake executable.

        The handler should accept args and **kwargs and return a tuple
        (returncode, stdout, stderr). If no handler is given, the
        executable will return (0, "", "")
        """
        if handler is None:
            handler = lambda args, **kwargs: (0, "", "")
        self._fake_executables[executable] = handler

    def check_call(self, command, **kwargs):
        returncode, stdout, stderr = self._call(command, **kwargs)
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, command)
        return returncode

    def check_output(self, command, **kwargs):
        returncode, stdout, stderr = self._call(command, **kwargs)
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, command, output=stdout)
        return stdout

    def _call(self, command, **kwargs):
        """Helper method for executing either a fake or real call.

        If a fake executable has been registered, use that one.
        Otherwise pass through the call to the real subprocess
        module.
        """
        self.calls.append((command, kwargs))
        handler = self._fake_executables.get(command[0])
        if handler is not None:
            return handler(command[1:], **kwargs)
        else:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **kwargs)
            stdout, stderr = process.communicate()
            return process.returncode, stdout, stderr
