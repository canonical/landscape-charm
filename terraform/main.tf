# © 2025 Canonical Ltd.

resource "juju_application" "landscape_server" {
  name  = var.app_name
  model = var.model

  charm {
    name     = "landscape-server"
    channel  = var.channel
    revision = var.revision
    base     = var.base
  }

  config      = var.config
  constraints = var.constraints
  units       = var.units
  trust       = true
}
