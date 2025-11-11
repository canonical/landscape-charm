# © 2025 Canonical Ltd.

locals {
  charm_name = "landcape-server"
}

resource "juju_application" "landscape_server" {
  name = var.app_name

  charm {
    name     = local.charm_name
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config      = var.config
  constraints = var.constraints
  units       = var.units
  trust       = true
  model  = var.model
}
