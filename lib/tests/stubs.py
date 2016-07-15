import subprocess

from charmhelpers.core.hookenv import Config


class HookenvStub(object):
    """Provide a testable stub for C{charmhelpers.core.hookenv}."""

    ip = "1.2.3.4"
    hook = "some-hook"
    unit = "landscape-server/0"
    relid = None
    leader = True

    def __init__(self, charm_dir):
        self.messages = []
        self.relations = {}
        self.action_fails = []
        self.action_sets = []
        self.statuses = [{"status": "unknown", "message": ""}]

        # We should disable implicit saving since it runs at charm exit using
        # globals :(
        self._config = Config()
        self._config.implicit_save = False

        self._charm_dir = charm_dir
        self.action_fails = []
        self.action_sets = []
        self.action_gets = []
        self._leader_data = {}

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

    def is_leader(self):
        return self.leader

    def leader_set(self, settings):
        self._leader_data = settings

    def leader_get(self):
        return self._leader_data

    def action_fail(self, message):
        self.action_fails.append(message)

    def action_set(self, values):
        self.action_sets.append(values)

    def action_get(self, key):
        self.action_gets.append(key)
        return "%s-value" % key

    def status_get(self):
        current_status = self.statuses[-1]
        return current_status["status"], current_status["message"]

    def status_set(self, workload_state, message):
        self.statuses.append({"status": workload_state, "message": message})


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
    add_fake_executable().

    @ivar calls: A list of all calls that have been made.
    """

    def __init__(self):
        self.calls = []
        self.processes = []
        self._fake_executables = {}

    def add_fake_executable(self, executable, args=None, stdout="", stderr="",
                            return_code=0):
        """Register a fake executable.

        @param executable: The full path of the executable to fake.
        @param args: Args that the executable should handle. If not
            provided, it will handle any arguments passed to it. It's
            possible to call this method multiple times with different
            arguments, if you want different behaviors for different
            arguments.
        @param stdout: The stdout the executable should return.
        @param stderr: The stderr the executable should return.
        @param return_code: The return code of the executable.
        """
        if args is not None:
            args = tuple(args)
        self._fake_executables.setdefault(executable, {})[args] = (
            return_code, stdout, stderr)

    def add_fake_script(self, script, stdout="", stderr="", return_code=0):
        """Register the fake results for a script."""
        args = None
        result = (return_code, stdout, stderr)
        self._fake_executables.setdefault(script, {})[args] = result

    def call(self, command, **kwargs):
        returncode, stdout, stderr = self._call(command, **kwargs)
        return returncode

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

    def Popen(self, args, **kwargs):

        class Popen(object):
            def communicate(process, input=None):
                process.input = input
                return self._call(args)

        process = Popen()
        process.kwargs = kwargs
        self.processes.append(process)
        return process

    def _call(self, command, **kwargs):
        """Helper method for executing either a fake or real call.

        If a fake executable has been registered, use that one.
        Otherwise pass through the call to the real subprocess
        module.
        """
        self.calls.append((command, kwargs))

        key = command
        if not isinstance(command, str):
            key = command[0]
        fake_command = self._fake_executables.get(key)
        if fake_command is not None:
            args = tuple(command[1:])
            if args not in fake_command:
                args = None
            return fake_command[args]
        else:
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **kwargs)
            stdout, stderr = process.communicate()
            return process.returncode, stdout, stderr


class PsutilUsageStub(object):
    """Testable stub for psutil.virtual_memory() return values."""
    def __init__(self, total):
        self.total = total


class PsutilStub(object):
    """Provide a testable stub for C{psutil}."""

    def __init__(self, num_cpus, physical_memory):
        self.NUM_CPUS = num_cpus
        self._physical_memory = physical_memory

    def virtual_memory(self):
        return PsutilUsageStub(self._physical_memory)
