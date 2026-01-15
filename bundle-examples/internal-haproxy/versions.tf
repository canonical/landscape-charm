# © 2026 Canonical Ltd.

terraform {
  required_version = ">= 1.10"
  required_providers {
    juju = {
      source  = "juju/juju"
      version = "1.1.1"
    }
  }
}
