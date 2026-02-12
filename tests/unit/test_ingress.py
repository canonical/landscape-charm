# Copyright 2026 Canonical Ltd

from unittest.mock import MagicMock

from ops.testing import Context, State

from charm import LandscapeServerCharm
import haproxy


def test_http_ingress_always_initialized(monkeypatch, apt_fixture):
    """
    Verify that http_ingress is always initialized regardless of config.
    """
    mock_ingress_cls = MagicMock()
    monkeypatch.setattr("charm.IngressPerAppRequirer", mock_ingress_cls)

    context = Context(LandscapeServerCharm)
    state = State(config={})

    with context(context.on.config_changed(), state) as mgr:
        charm = mgr.charm

        assert hasattr(charm, "http_ingress")

        call_kwargs = [call.kwargs for call in mock_ingress_cls.call_args_list]

        http = next(k for k in call_kwargs if k.get("relation_name") == "http-ingress")
        assert http["port"] == haproxy.FrontendPort.HTTP
        assert "scheme" not in http


def test_ingress_config_enabled(monkeypatch, apt_fixture):
    """
    Verify that when config is enabled, the charm initializes the ingress
    attributes correctly.
    """
    mock_ingress_cls = MagicMock()
    monkeypatch.setattr("charm.IngressPerAppRequirer", mock_ingress_cls)

    context = Context(LandscapeServerCharm)
    state = State(
        config={
            "enable_hostagent_messenger": True,
            "enable_ubuntu_installer_attach": True,
        }
    )

    with context(context.on.config_changed(), state) as mgr:
        charm = mgr.charm

        assert hasattr(charm, "hostagent_messenger_ingress")
        assert hasattr(charm, "ubuntu_installer_attach_ingress")

        call_kwargs = [call.kwargs for call in mock_ingress_cls.call_args_list]

        hostagent = next(
            k
            for k in call_kwargs
            if k.get("relation_name") == "hostagent-messenger-ingress"
        )
        assert hostagent["port"] == haproxy.FrontendPort.HOSTAGENT_MESSENGER

        installer = next(
            k
            for k in call_kwargs
            if k.get("relation_name") == "ubuntu-installer-attach-ingress"
        )
        assert installer["port"] == haproxy.FrontendPort.UBUNTU_INSTALLER_ATTACH


def test_ingress_config_disabled(monkeypatch, apt_fixture):
    """
    Verify that when config is disabled, the charm does NOT create the attributes.
    """
    mock_ingress_cls = MagicMock()
    monkeypatch.setattr("charm.IngressPerAppRequirer", mock_ingress_cls)

    context = Context(LandscapeServerCharm)
    state = State(
        config={
            "enable_hostagent_messenger": False,
            "enable_ubuntu_installer_attach": False,
        }
    )

    with context(context.on.config_changed(), state) as mgr:
        charm = mgr.charm

        assert not hasattr(charm, "hostagent_messenger_ingress")
        assert not hasattr(charm, "ubuntu_installer_attach_ingress")

        assert mock_ingress_cls.call_count == 1
