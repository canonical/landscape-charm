from ops.testing import Relation, State
import yaml


def get_haproxy_services(state: State, relation: Relation) -> list[dict]:
    """
    Return the services configured in the HAProxy relation with Landscape server.
    """
    raw_services = state.get_relation(relation.id).local_unit_data["services"]
    services = yaml.safe_load(raw_services)

    assert isinstance(services, list)
    assert len(services) > 0
    assert isinstance(services[0], dict)

    return services
