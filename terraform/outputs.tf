# © 2025 Canonical Ltd.

# The follow outputs are meant to conform with Canonical's standards for 
# charm modules in a Terraform ecosystem (CC006).

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.landscape_server.name
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

locals {
  # Needed since the relations changed to support the hostagent services
  legacy_amqp_rel_channels = ["latest/stable", "latest/beta", "latest/edge", "24.04/edge"]
  using_legacy_amqp_rel    = contains(local.legacy_amqp_rel_channels, var.channel) || (var.revision != null && var.revision <= 141)
  amqp_relations           = local.using_legacy_amqp_rel ? { amqp = "amqp" } : { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" }
}

output "requires" {
  value = merge({
    application_dashboard = "application-dashboard"
    db                    = "db"
    database              = "database"
  }, local.amqp_relations)
}
