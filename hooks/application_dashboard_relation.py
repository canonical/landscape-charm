#!/usr/bin/python
# Copyright Canonical 2021 Canonical Ltd. All Rights Reserved
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
import sys
import os

from charmhelpers.core.hookenv import (
    log,
    relation_set,
    relation_get,
    relation_ids,
    related_units,
    is_leader,
    Hooks,
    unit_public_ip,
    UnregisteredHookError,
    config,
)

hooks = Hooks()


@hooks.hook("application-dashboard-relation-joined")
@hooks.hook("application-dashboard-relation-changed")
def application_dashboard_relation_changed(relation_id=None, remote_unit=None):
    """Register Landscape URL in dashboard charm such as Homer."""
    if not is_leader():
        return
    relations = relation_ids('application-dashboard')
    if not relations:
        return

    url = None
    if config("root-url"):
        url = config("root-url")
    else:
        public_ip = None
        for rid in relation_ids("website"):
            haproxy_units = related_units(rid)
            for hap_unit in haproxy_units:
                public_ip = relation_get("public-address",
                                         unit=hap_unit,
                                         rid=rid)
                break
            if public_ip:
                break
        if public_ip is None:
            public_ip = unit_public_ip()
        # Landscape UI always uses https.
        scheme = "https://"
        url = scheme + public_ip

    if config("site-name"):
        subtitle = "[{}] Systems management".format(config("site-name"))
        group = "[{}] LMA".format(config("site-name"))
    else:
        subtitle = "Systems management"
        group = "LMA"

    icon_data = None
    icon_file = os.environ.get("JUJU_CHARM_DIR", "") + "/icon.svg"
    if os.path.exists(icon_file):
        with open(icon_file) as f:
            icon_data = f.read()
    for rid in relations:
        relation_set(
            rid,
            relation_settings={
                "name": "Landscape",
                "url": url,
                "subtitle": subtitle,
                "icon": icon_data,
                "group": group,
                },
            app=True,
        )


if __name__ == "__main__":
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log("Unknown hook {} - skipping.".format(e))
