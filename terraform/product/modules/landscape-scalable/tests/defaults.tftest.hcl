# © 2025 Canonical Ltd.

mock_provider "juju" {}

variables {
  model            = "test-landscape"
  landscape_server = {}
  haproxy          = {}
  postgresql       = {}
  rabbitmq_server  = {}
}

run "validate_channel_defaults" {
  command = plan

  assert {
    condition     = var.landscape_server.channel == "25.10/beta"
    error_message = "Landscape Server channel should default to '25.10/beta'"
  }

  assert {
    condition     = var.postgresql.channel == "14/stable"
    error_message = "PostgreSQL channel should default to '14/stable'"
  }

  assert {
    condition     = var.haproxy.channel == "latest/edge"
    error_message = "HAProxy channel should default to 'latest/edge'"
  }

  assert {
    condition     = var.rabbitmq_server.channel == "latest/edge"
    error_message = "RabbitMQ channel should default to 'latest/edge'"
  }
}

run "validate_rev_defaults" {
  command = plan

  assert {
    condition     = var.landscape_server.revision == null
    error_message = "Landscape Server revision should default to null"
  }

  assert {
    condition     = var.postgresql.revision == null
    error_message = "PostgreSQL revision should default to null"
  }

  assert {
    condition     = var.haproxy.revision == null
    error_message = "HAProxy revision should default to null"
  }

  assert {
    condition     = var.rabbitmq_server.revision == null
    error_message = "RabbitMQ revision should default to null"
  }
}

run "validate_base_defaults" {
  command = plan

  assert {
    condition     = var.landscape_server.base == "ubuntu@22.04"
    error_message = "Landscape Server base should default to 'ubuntu@22.04'"
  }

  assert {
    condition     = var.postgresql.base == "ubuntu@22.04"
    error_message = "PostgreSQL base should default to 'ubuntu@22.04'"
  }

  assert {
    condition     = var.haproxy.base == "ubuntu@22.04"
    error_message = "HAProxy base should default to 'ubuntu@22.04'"
  }

  assert {
    condition     = var.rabbitmq_server.base == "ubuntu@24.04"
    error_message = "RabbitMQ base should default to 'ubuntu@24.04'"
  }
}

run "validate_config_defaults" {
  command = plan

  assert {
    condition     = lookup(var.landscape_server.config, "autoregistration", null) == "true"
    error_message = "Landscape Server should have autoregistration enabled by default"
  }

  assert {
    condition     = lookup(var.landscape_server.config, "landscape_ppa", null) == "ppa:landscape/self-hosted-beta"
    error_message = "Landscape Server should default to ppa:landscape/self-hosted-beta"
  }

  assert {
    condition     = lookup(var.postgresql.config, "plugin_plpython3u_enable", null) == "true"
    error_message = "PostgreSQL should have plpython3u plugin enabled by default"
  }

  assert {
    condition     = lookup(var.rabbitmq_server.config, "consumer-timeout", null) == "259200000"
    error_message = "RabbitMQ should have consumer-timeout set to 259200000 by default"
  }

  assert {
    condition     = lookup(var.haproxy.config, "ssl_cert", null) == "SELFSIGNED"
    error_message = "HAProxy should use SELFSIGNED SSL cert by default"
  }
}

run "validate_constraints_defaults" {
  command = plan

  assert {
    condition     = var.landscape_server.constraints == "arch=amd64"
    error_message = "Landscape Server constraints should default to 'arch=amd64'"
  }

  assert {
    condition     = var.postgresql.constraints == "arch=amd64"
    error_message = "PostgreSQL constraints should default to 'arch=amd64'"
  }

  assert {
    condition     = var.haproxy.constraints == "arch=amd64"
    error_message = "HAProxy constraints should default to 'arch=amd64'"
  }

  assert {
    condition     = var.rabbitmq_server.constraints == "arch=amd64"
    error_message = "RabbitMQ constraints should default to 'arch=amd64'"
  }
}
