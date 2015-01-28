from charmhelpers.core.services.base import ServiceManager
from charmhelpers.core.services.helpers import render_template

from lib.hook import Hook
from lib.relations.postgresql import PostgreSQLRelation


class ServicesHook(Hook):
    """Execute service configuration logic.

    This hook uses the charm-helpers service framework to determine if we got
    all relation data we need in order to configure this Landscape unit, and
    proceed with the configuration if ready.
    """

    def _run(self):
        manager = ServiceManager([{
            "service": "landscape",
            "ports": [],
            "provided_data": [],
            "required_data": [PostgreSQLRelation()],
            "data_ready": [
                render_template(
                    owner="landscape", group="root", perms=0o640,
                    source="service.conf",
                    target="/etc/landscape/service.conf")
            ],
        }])
        manager.manage()
