import application_dashboard_relation

import mock


@mock.patch("application_dashboard_relation.relation_set")
@mock.patch("application_dashboard_relation.unit_public_ip")
@mock.patch("application_dashboard_relation.is_leader")
@mock.patch("application_dashboard_relation.relation_ids")
@mock.patch("application_dashboard_relation.config")
@mock.patch("os.environ.get")
def test_main(
    environ_get, config, relation_ids, is_leader, unit_public_ip, relation_set
):
    hostname = "landscape.com"
    unit_public_ip.return_value = hostname
    relation_id = "application-dashboard:0"
    environ_get.return_value = ""
    relation_ids.return_value = relation_id
    site_name = "test"
    config.return_value = site_name
    application_dashboard_relation.application_dashboard_relation_changed()
    subtitle = "[{}] Systems management".format(site_name)
    group = "[{}] LMA".format(site_name)
    name = "Landscape"
    tls_configured = config("ssl_key")
    scheme = "https" if tls_configured else "http"

    relation_set.assert_called_with(
        "0",
        app=True,
        relation_settings={
            "name": name,
            "url": "{}://{}".format(scheme, hostname),
            "subtitle": subtitle,
            "icon": None,
            "group": group,
        },
    )
