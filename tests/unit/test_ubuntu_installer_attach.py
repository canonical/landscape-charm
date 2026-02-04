# Copyright 2026 Canonical Ltd

"""Unit tests for `_configure_ubuntu_installer_attach`."""

from unittest.mock import patch

from charms.operator_libs_linux.v0.apt import PackageError
from ops.model import MaintenanceStatus
from ops.testing import Context, State, StoredState

from charm import LandscapeServerCharm


class TestConfigureUbuntuInstallerAttach:
    def test_disable_with_package_error(self, apt_fixture, lb_certs_state):
        """PackageError on disable keeps state unchanged and logs error."""
        _, remove_package_mock = apt_fixture
        remove_package_mock.side_effect = PackageError("Failed to remove package")

        ctx = Context(LandscapeServerCharm)
        state_in = State(
            **lb_certs_state,
            config={"enable_ubuntu_installer_attach": False},
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={"enable_ubuntu_installer_attach": True},
                )
            ],
        )

        with patch("charm.logger") as mock_logger:
            state_out = ctx.run(ctx.on.config_changed(), state_in)

            assert any(
                "Failed to remove ubuntu installer attach" in str(call)
                for call in mock_logger.error.call_args_list
            )

        stored = state_out.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        )
        assert isinstance(state_out.unit_status, MaintenanceStatus)
        assert (
            "Failed to enable `landscape-ubuntu-installer-attach`"
            in state_out.unit_status.message
        )
        assert stored.content.get("enable_ubuntu_installer_attach") is True

    def test_enable_with_package_error(self, apt_fixture, lb_certs_state):
        """PackageError on enable keeps state unchanged and logs error."""
        add_package_mock, _ = apt_fixture
        error_message = "Detailed package installation error"
        add_package_mock.side_effect = PackageError(error_message)

        ctx = Context(LandscapeServerCharm)
        state_in = State(
            **lb_certs_state,
            config={"enable_ubuntu_installer_attach": True},
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={"enable_ubuntu_installer_attach": False},
                )
            ],
        )

        with patch("charm.logger") as mock_logger:
            state_out = ctx.run(ctx.on.config_changed(), state_in)

            mock_logger.error.assert_called()
            call_args = [str(call) for call in mock_logger.error.call_args_list]
            assert any(
                "Failed to install ubuntu installer attach" in arg for arg in call_args
            )

        stored = state_out.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        )
        assert isinstance(state_out.unit_status, MaintenanceStatus)
        assert (
            "Failed to enable `landscape-ubuntu-installer-attach`"
            in state_out.unit_status.message
        )
        assert stored.content.get("enable_ubuntu_installer_attach") is False
