# © 2025 Canonical Ltd.

# The following outputs are meant to conform with Canonical's standards for 
# charm modules in a Terraform ecosystem (CC006).

output "app_name" {
  description = "Name of the deployed application."
  value       = juju_application.landscape_server.name
}

output "provides" {
  description = " Map of integration endpoints this charm provides (`cos-agent`, `data`, `hosted`, `nrpe-external-master`, `website`)."
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
  amqp_rels_updated_rev    = 142
  has_modern_amqp_rels     = !contains(local.legacy_amqp_rel_channels, var.channel) && (var.revision != null ? var.revision >= local.amqp_rels_updated_rev : true)
  amqp_relations           = local.has_modern_amqp_rels ? { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" } : { amqp = "amqp" }
}

output "requires" {
  description = "Map of integration endpoints this charm requires (`application-dashboard`, `db`, `amqp` or `inbound-amqp`/`outbound-amqp`)."
  value = merge({
    application_dashboard = "application-dashboard",
    db                    = "db"
  }, local.amqp_relations)
}
