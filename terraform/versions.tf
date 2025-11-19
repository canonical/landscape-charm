# © 2025 Canonical Ltd.

terraform {
  required_version = ">= 1.10"
  required_providers {
    juju = {
      source = "juju/juju"
      # NOTE: contains breaking changes
      version = "< 1.0.0"
    }
  }
}
