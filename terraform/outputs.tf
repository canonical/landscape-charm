# © 2025 Canonical Ltd.
# See LICENSE file for licensing details.

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.landscape_server.name
}

output "requires" {
  value = merge({
    application_dashboard = "application-dashboard"
    db                    = "db"
  }, local.amqp_relations)
}

output "provides" {
  value = {
    cos_agent            = "cos-agent"
    data                 = "data"
    hosted               = "hosted"
    nrpe_external_master = "nrpe-external-master"
    website              = "website"
  }
}
