terraform {
  required_version = ">= 1.6"
  required_providers {
    juju = {
      source  = "juju/juju"
      version = "~> 0.14.0"
    }
    external = {
      source  = "hashicorp/external"
      version = "~> 2.3.4"
    }
  }
}
