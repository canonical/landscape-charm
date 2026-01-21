# © 2025 Canonical Ltd.

terraform {
  required_version = ">= 1.10"
  required_providers {
    juju = {
      source = "juju/juju"
      # NOTE: 1.0 contains breaking changes that required modules have
      # yet to handle.
      version = "< 1.0.0"
    }
  }
}
