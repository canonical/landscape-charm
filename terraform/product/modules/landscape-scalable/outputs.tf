# © 2025 Canonical Ltd.

output "registration_key" {
  description = "Registration key from the Landscape Server config."
  value       = lookup(var.landscape_server.config, "registration_key", null)
}

output "admin_email" {
  description = "Administrator email from the Landscape Server config."
  value       = lookup(var.landscape_server.config, "admin_email", null)
}

output "admin_password" {
  description = "Administrator password from the Landscape Server config (sensitive)."
  value       = lookup(var.landscape_server.config, "admin_password", null)
  sensitive   = true
}

output "applications" {
  description = "The charms included in the module."
  value = {
    landscape_server = module.landscape_server
    haproxy          = module.haproxy
    postgresql       = module.postgresql
    rabbitmq_server  = juju_application.rabbitmq_server
  }
}

locals {
  haproxy_self_signed = (
    lookup(var.haproxy.config, "ssl_key", null) == null ||
    lookup(var.haproxy.config, "ssl_cert", null) == null ||
    lookup(var.haproxy.config, "ssl_cert", null) == "SELFSIGNED"
  )
}

output "haproxy_self_signed" {
  description = "Indicates whether HAProxy is using a self-signed TLS certificate."
  value       = local.haproxy_self_signed
}

output "has_modern_amqp_relations" {
  description = "Indicates whether the deployment uses the modern inbound/outbound AMQP endpoints."
  value       = local.has_modern_amqp_relations
}
