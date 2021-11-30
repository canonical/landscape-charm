import os.path

from charmhelpers.core import hookenv
from charmhelpers.core.services.helpers import RelationContext


class ApplicationDashboardProvider(RelationContext):
    """Relation data provider feeding application dashboard configuration."""

    name = "application-dashboard"
    interface = "register-application"

    def __init__(self, config_requirer, hookenv=hookenv):
        self._config_requirer = config_requirer
        self._hookenv = hookenv
        super(ApplicationDashboardProvider, self).__init__()

    def provide_data(self):
        if not self._hookenv.is_leader():
            return

        url = None
        config = self._hookenv.config()
        if config["root-url"]:
            url = config["root-url"]
        else:
            public_ip = None
            for rid in self._hookenv.relation_ids("website"):
                haproxy_units = self._hookenv.related_units(rid)
                for hap_unit in haproxy_units:
                    public_ip = self._hookenv.relation_get(
                        "public-address",
                        unit=hap_unit,
                        rid=rid)
                    break
                if public_ip:
                    break
            if public_ip is None:
                public_ip = self._hookenv.unit_public_ip()
            # Landscape UI always uses https.
            scheme = "https://"
            url = scheme + public_ip

        if config["site-name"]:
            subtitle = "[{}] Systems management".format(config["site-name"])
            group = "[{}] LMA".format(config["site-name"])
        else:
            subtitle = "Systems management"
            group = "LMA"

        icon_data = None
        icon_file = (self._hookenv.charm_dir() or "") + "/icon.svg"
        if os.path.exists(icon_file):
            with open(icon_file) as f:
                icon_data = f.read()
        return {
            "name": "Landscape",
            "url": url,
            "subtitle": subtitle,
            "icon": icon_data,
            "group": group,
        }
