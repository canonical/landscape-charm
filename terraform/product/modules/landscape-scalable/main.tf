# © 2026 Canonical Ltd.

module "landscape_server" {
  source      = "../../../charm"
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
  source          = "git::https://github.com/canonical/postgresql-operator.git//terraform?ref=v16/1.135.0"
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

locals {
  has_modern_pg_interface = can(module.landscape_server.requires.database)
}


resource "juju_integration" "landscape_server_postgresql_legacy" {
  model = var.model

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.db
  }

  application {
    name     = module.postgresql.application_name
    endpoint = "db-admin"
  }

  count = local.has_modern_pg_interface ? 0 : 1

  depends_on = [module.landscape_server, module.postgresql]

}

resource "juju_integration" "landscape_server_postgresql_modern" {
  model = var.model

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.database
  }

  application {
    name     = module.postgresql.application_name
    endpoint = module.postgresql.provides.database
  }

  depends_on = [module.landscape_server, module.postgresql]

  count = local.has_modern_pg_interface ? 1 : 0

}
