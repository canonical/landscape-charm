from unittest.mock import patch

from ops.testing import Context, Relation, State, StoredState
import yaml

from charm import LANDSCAPE_UBUNTU_INSTALLER_ATTACH, LandscapeServerCharm

MODULE = "src.charm"


class TestUbuntuInstallerAttach:

    @patch(MODULE + ".apt.add_package")
    def test_enable(self, mock_add_package):
        """
        If the Ubuntu installer attach service is enabled, add the HAProxy frontend
        and install the service.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={"root_url": "https//root.test"},
            relations=[relation],
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={"enable_ubuntu_installer_attach": False},
                )
            ],
        )
        assert not state_in.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        ).content.get("enable_ubuntu_installer_attach")

        state_out = context.run(
            event=context.on.action("enable-ubuntu-installer-attach"),
            state=state_in,
        )

        services = _get_haproxy_services(state_out, relation)
        service_names = (s["service_name"] for s in services)

        assert "landscape-ubuntu-installer-attach" in service_names
        assert state_out.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        ).content.get("enable_ubuntu_installer_attach")
        mock_add_package.assert_called_once_with(
            LANDSCAPE_UBUNTU_INSTALLER_ATTACH,
            update_cache=True,
        )

    @patch(MODULE + ".apt.remove_package")
    def test_disable(self, mock_remove_package):
        """
        If the Ubuntu installer attach service is disabled, remove the HAProxy
        frontend and uninstall the service.
        """
        context = Context(LandscapeServerCharm)
        relation = Relation("website")
        state_in = State(
            config={"root_url": "https//root.test"},
            relations=[relation],
            stored_states=[
                StoredState(
                    owner_path="LandscapeServerCharm",
                    content={"enable_ubuntu_installer_attach": True},
                )
            ],
        )
        assert state_in.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        ).content.get("enable_ubuntu_installer_attach")

        state_out = context.run(
            event=context.on.action("disable-ubuntu-installer-attach"),
            state=state_in,
        )

        services = _get_haproxy_services(state_out, relation)
        service_names = (s["service_name"] for s in services)

        assert "landscape-ubuntu-installer-attach" not in service_names
        assert not state_out.get_stored_state(
            "_stored", owner_path="LandscapeServerCharm"
        ).content.get("enable_ubuntu_installer_attach")
        mock_remove_package.assert_called_once_with(LANDSCAPE_UBUNTU_INSTALLER_ATTACH)


def _get_haproxy_services(state: State, relation: Relation) -> list[dict]:
    """
    Return the services configured in the HAProxy relation with Landscape server.
    """
    raw_services = state.get_relation(relation.id).local_unit_data["services"]
    services = yaml.safe_load(raw_services)

    assert isinstance(services, list)
    assert len(services) > 0
    assert isinstance(services[0], dict)

    return services
