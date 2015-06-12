import os
import yaml

from charmhelpers.core import hookenv


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
