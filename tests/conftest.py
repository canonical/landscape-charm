from configparser import ConfigParser

import pytest

import settings_files


class ConfigReader:

    def __init__(self, tempfile):
        self.tempfile = tempfile

    def get_config(self) -> ConfigParser:
        config = ConfigParser()
        config.read(self.tempfile)
        return config


@pytest.fixture
def capture_service_conf(tmp_path, monkeypatch) -> ConfigReader:
    """
    Redirect all writes to `SERVICE_CONF` to a tempfile within this fixture.
    Return a `ConfigReader` that reads from this file.
    """
    conf_file = tmp_path / "service.conf"
    conf_file.write_text("")

    monkeypatch.setattr(settings_files, "SERVICE_CONF", str(conf_file))

    return ConfigReader(conf_file)
