# © 2025 Canonical Ltd.

module "landscape_server" {
  # TODO: Pin to real release when we get one with these fixes
  source      = "git::https://github.com/jansdhillon/landscape-charm.git//terraform?ref=update-tf-module"
  model       = var.model
  config      = var.landscape_server.config
  app_name    = var.landscape_server.app_name
  channel     = var.landscape_server.channel
  constraints = var.landscape_server.constraints
  revision    = var.landscape_server.revision
  base        = var.landscape_server.base
  units       = var.landscape_server.units
}

module "haproxy" {
  source      = "git::https://github.com/canonical/haproxy-operator.git//terraform/charm?ref=rev250"
  model       = var.model
  config      = var.haproxy.config
  app_name    = var.haproxy.app_name
  channel     = var.haproxy.channel
  constraints = var.haproxy.constraints
  revision    = var.haproxy.revision
  base        = var.haproxy.base
  units       = var.haproxy.units
}

module "postgresql" {
  source          = "git::https://github.com/canonical/postgresql-operator.git//terraform?ref=rev935"
  juju_model_name = var.model
  config          = var.postgresql.config
  app_name        = var.postgresql.app_name
  channel         = var.postgresql.channel
  constraints     = var.postgresql.constraints
  revision        = var.postgresql.revision
  base            = var.postgresql.base
  units           = var.postgresql.units
}

# TODO: Replace with internal charm module if/when it's created
resource "juju_application" "rabbitmq_server" {
  name        = var.rabbitmq_server.app_name
  model       = var.model
  units       = var.rabbitmq_server.units
  constraints = var.rabbitmq_server.constraints
  config      = var.rabbitmq_server.config

  charm {
    name     = var.rabbitmq_server.app_name
    revision = var.rabbitmq_server.revision
    channel  = var.rabbitmq_server.channel
    base     = var.rabbitmq_server.base
  }
}

locals {
  has_modern_amqp_relations = can(module.landscape_server.requires.inbound_amqp) && can(module.landscape_server.requires.outbound_amqp)
}

resource "juju_integration" "landscape_server_inbound_amqp" {
  model = var.model

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.inbound_amqp
  }

  application {
    name = juju_application.rabbitmq_server.name
  }

  depends_on = [module.landscape_server, juju_application.rabbitmq_server]

  count = local.has_modern_amqp_relations ? 1 : 0
}

resource "juju_integration" "landscape_server_outbound_amqp" {
  model = var.model

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.outbound_amqp
  }

  application {
    name = juju_application.rabbitmq_server.name
  }

  depends_on = [module.landscape_server, juju_application.rabbitmq_server]

  count = local.has_modern_amqp_relations ? 1 : 0
}

# TODO: update when RMQ charm module exists
resource "juju_integration" "landscape_server_rabbitmq_server" {
  model = var.model

  application {
    name = module.landscape_server.app_name
  }

  application {
    name = juju_application.rabbitmq_server.name
  }

  depends_on = [module.landscape_server, juju_application.rabbitmq_server]

  count = local.has_modern_amqp_relations ? 0 : 1
}

resource "juju_integration" "landscape_server_haproxy" {
  model = var.model

  application {
    name = module.landscape_server.app_name
  }

  application {
    name = module.haproxy.app_name
  }

  depends_on = [module.landscape_server, module.haproxy]

}

# TODO: Handle both interfaces when the Landscape Charm can integrate with the modern
# PostgreSQL interface (postgresql_client). See the `modern-pg-interface` branch.
resource "juju_integration" "landscape_server_postgresql" {
  model = var.model

  application {
    name     = module.landscape_server.app_name
    endpoint = "db"
  }

  application {
    name     = module.postgresql.application_name
    endpoint = "db-admin"
  }

  depends_on = [module.landscape_server, module.postgresql]

}
