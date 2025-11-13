# © 2025 Canonical Ltd.

# The following outputs are meant to conform with Canonical's standards for 
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
  amqp_rels_updated_rev    = 142
  has_modern_amqp_rels     = !contains(local.legacy_amqp_rel_channels, var.channel) && (var.revision != null ? var.revision >= local.amqp_rels_updated_rev : true)
  amqp_relations           = local.has_modern_amqp_rels ? { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" } : { amqp = "amqp" }

  # Map bases to the revision when they were updated to use the modern Postgres charm interface
  pg_interface_updated_base_rev_map = { "ubuntu@22.04" : 210 }
  default_pg_interface_updated_rev  = 211
  pg_interface_updated_rev          = lookup(local.pg_interface_updated_base_rev_map, var.base, local.default_pg_interface_updated_rev)
  has_modern_pg_interface           = var.revision != null ? var.revision >= local.pg_interface_updated_rev : true
  database_relations                = local.has_modern_pg_interface ? { db = "db", database = "database" } : { db = "db" }
}

output "requires" {
  value = merge({
    application_dashboard = "application-dashboard"
  }, local.database_relations, local.amqp_relations)
}
