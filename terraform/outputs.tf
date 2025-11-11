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
  # NOTE: The logic for the legacy/modern AMQP rels vs the legacy/modern DB rels
  # is different because the (Landscape) charm supports both the modern and legacy PostgreSQL
  # charm interfaces, but can only support either the legacy or modern AMQP charm interface.

  # Needed since the relations changed to support the hostagent services
  legacy_amqp_rel_channels = ["latest/stable", "latest/beta", "latest/edge", "24.04/edge"]
  using_legacy_amqp_rel    = contains(local.legacy_amqp_rel_channels, var.channel) || (var.revision != null && var.revision <= 141)
  amqp_relations           = local.using_legacy_amqp_rel ? { amqp = "amqp" } : { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" }

  # Enable the integration only for charm revisions that have the `database` relation.
  modern_postgres_interface_support_added_rev = 213
  has_modern_pg_interface                     = var.revision < local.modern_postgres_interface_support_added_rev
  database_relations                          = local.has_modern_pg_interface ? { db = "db" } : { db = "db", database = "database" }
}

output "requires" {
  value = merge({
    application_dashboard = "application-dashboard"
  }, local.database_relations, local.amqp_relations)
}
