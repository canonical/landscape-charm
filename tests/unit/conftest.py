from configparser import ConfigParser
from unittest.mock import patch

import pytest

import settings_files


class ConfigReader:

    def __init__(self, tempfile):
        self.tempfile = tempfile

    def get_config(self) -> ConfigParser:
        config = ConfigParser()
        config.read(self.tempfile)
        return config


@pytest.fixture(autouse=True)
def capture_service_conf(tmp_path, monkeypatch) -> ConfigReader:
    """
    Redirect all writes to `SERVICE_CONF` to a tempfile within this fixture.
    Return a `ConfigReader` that reads from this file.

    This is set to `autouse=True` to avoid any attempts to write to the filesystem
    during tests, which typically throw an error if the real
    `/etc/landscape/service.conf` is not present.
    """
    conf_file = tmp_path / "service.conf"
    conf_file.write_text("")

    monkeypatch.setattr(settings_files, "SERVICE_CONF", str(conf_file))

    return ConfigReader(conf_file)


@pytest.fixture(autouse=True)
def get_haproxy_error_files():
    """
    Return empty HAProxy error files.

    This is set to `autouse=True` to avoid any attempts to read the HAProxy error files
    from their installed location in /opt/canonical/...`, which is not present in a test
    environment.
    """

    with patch("charm._get_haproxy_error_files") as m:
        m.return_value = ()
        yield m
