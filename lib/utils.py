import os
import subprocess
import yaml

from charmhelpers.core import hookenv

from lib.error import CharmError


def is_valid_url(value):
    """
    A helper to validate a string is a URL suitable to use as root-url.
    """
    if not value[-1] == "/":
        return False
    if not value.startswith("http"):
        return False
    if "://" not in value:
        return False

    return True


def get_required_data(manager, service_name, key):
    """Get the service manager required_data entry matching the given key.

    This function will scan the required_data of the given ServiceManager
    and search for an entry matching the given key.

    @param manager: A ServiceManager instance.
    @param service_name: The name of the service on which to access data. In
        this charm's case, it is always "landscape", but simply passing the
        service_name given to a callback's __call__ is safer.
    @param key: The key for the particular value we are looking for inside all
        of the service's required_data.
    """
    service = manager.get_service(service_name)
    for data in service["required_data"]:
        if key in data:
            return data[key]


def update_persisted_data(key, value, hookenv=hookenv):
    """Persist the given 'value' for the given 'key' and return the old value.

    This function manages a local key->value store that can be used to persist
    data and compare it against previous versions.

    @param key: The key to update.
    @param value: The value to persist.
    @return: The old value of the key, or None if it's a new value.
    """
    filename = os.path.join(hookenv.charm_dir(), ".landscape-persisted-data")
    if os.path.exists(filename):
        with open(filename) as fd:
            data = yaml.load(fd)
    else:
        data = {}
    old = data.get(key, None)
    data[key] = value
    with open(filename, "w") as fd:
        data = yaml.dump(data, fd)
    return old


class CommandRunner(object):
    """A landscape-charm-specific wrapper around subprocess.

    All calls are logged and failures are converted into CharmError (as
    well as logging the return code).
    """

    def __init__(self, hookenv=hookenv, subprocess=subprocess):
        self._hookenv = hookenv
        self._subprocess = subprocess
        self._cwd = None

    def in_dir(self, dirname):
        """Return a new runner that runs commands in the given directory."""
        runner = self.__class__(hookenv=self._hookenv,
                                subprocess=self._subprocess)
        runner._cwd = dirname
        return runner

    def _run(self, args, shell=False):
        kwargs = {}
        if shell:
            kwargs.update(shell=True)
        if self._cwd:
            kwargs.update(cwd=self._cwd)
        cmdstr = args if isinstance(args, str) else ' '.join(args)

        self._hookenv.log('running {!r}'.format(cmdstr),
                          level=hookenv.DEBUG)
        try:
            self._subprocess.check_call(args, **kwargs)
        except subprocess.CalledProcessError as err:
            self._hookenv.log('got return code {} running {!r}'
                              .format(err.returncode, cmdstr),
                              level=hookenv.ERROR)
            raise CharmError('command failed (see unit logs): {}'
                             .format(cmdstr))

    def run(self, cmd, *args):
        """Run cmd with the given arguments."""
        args = list(args)
        args.insert(0, cmd)
        self._run(args)

    def shell(self, script):
        """Run a shell script."""
        self._run(script, shell=True)
