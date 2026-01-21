# © 2025 Canonical Ltd.

mock_provider "juju" {}

variables {
  model = "test-landscape"
  landscape_server = {
    revision = 150
  }
  haproxy         = {}
  postgresql      = {}
  rabbitmq_server = {}
}

run "test_local_has_modern_amqp_relations_true" {
  command = plan

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        inbound_amqp  = "inbound-amqp"
        outbound_amqp = "outbound-amqp"
        database      = "database"
        db            = "db"
      }
    }
  }

  assert {
    condition     = local.has_modern_amqp_relations == true
    error_message = "has_modern_amqp_relations should be true when both inbound_amqp and outbound_amqp exist"
  }

  assert {
    condition     = can(module.landscape_server.requires.inbound_amqp) && can(module.landscape_server.requires.outbound_amqp)
    error_message = "Both inbound_amqp and outbound_amqp should be accessible via can()"
  }
}

run "test_local_has_modern_amqp_relations_false" {
  command = plan

  override_module {
    target = module.landscape_server
    outputs = {
      app_name = "landscape-server"
      requires = {
        database = "database"
        db       = "db"
      }
    }
  }

  assert {
    condition     = local.has_modern_amqp_relations == false
    error_message = "`has_modern_amqp_relations` should be false when inbound_amqp or outbound_amqp don't exist"
  }

  assert {
    condition     = !can(module.landscape_server.requires.inbound_amqp) && !can(module.landscape_server.requires.outbound_amqp)
    error_message = "Neither inbound_amqp nor outbound_amqp should be accessible when has_modern_amqp_relations is false"
  }
}


run "test_modern_amqp_interfaces" {
  command = plan

  assert {
    condition = (
      local.has_modern_amqp_relations == true ?
      (
        length(juju_integration.landscape_server_inbound_amqp) == 1 &&
        length(juju_integration.landscape_server_outbound_amqp) == 1
      ) : true
    )
    error_message = "When has_modern_amqp_relations is true, both modern AMQP relations should be created"
  }

  assert {
    condition = (
      local.has_modern_amqp_relations == true ?
      length(juju_integration.landscape_server_rabbitmq_server) == 0 : true
    )
    error_message = "When has_modern_amqp_relations is true, legacy relation should not be created"
  }
}

run "test_legacy_amqp_interface" {
  command = plan

  assert {
    condition = (
      local.has_modern_amqp_relations == false ?
      length(juju_integration.landscape_server_rabbitmq_server) == 1 : true
    )
    error_message = "When has_modern_amqp_relations is false, legacy relation should be created"
  }

  assert {
    condition = (
      local.has_modern_amqp_relations == false ?
      (
        length(juju_integration.landscape_server_inbound_amqp) == 0 &&
        length(juju_integration.landscape_server_outbound_amqp) == 0
      ) : true
    )
    error_message = "When has_modern_amqp_relations is false, modern AMQP relations should not be created"
  }
}


run "validate_all_modules_created" {
  command = plan

  assert {
    condition     = module.landscape_server != null
    error_message = "Landscape server module should be created"
  }

  assert {
    condition     = module.haproxy != null
    error_message = "HAProxy module should be created"
  }

  assert {
    condition     = module.postgresql != null
    error_message = "PostgreSQL module should be created"
  }

  assert {
    condition     = juju_application.rabbitmq_server != null
    error_message = "RabbitMQ application should be created"
  }
}

run "validate_all_integrations_created" {
  command = plan

  assert {
    condition     = juju_integration.landscape_server_haproxy != null
    error_message = "Landscape-HAProxy integration should be created"
  }

  assert {
    condition     = juju_integration.landscape_server_postgresql != null
    error_message = "Landscape-PostgreSQL integration should be created"
  }

  assert {
    condition = (
      length(juju_integration.landscape_server_rabbitmq_server) > 0 ||
      (
        length(juju_integration.landscape_server_inbound_amqp) > 0 &&
        length(juju_integration.landscape_server_outbound_amqp) > 0
      )
    )
    error_message = "At least one AMQP integration pattern should be created (legacy single or modern combo)"
  }
}

run "validate_no_pg16_stable_allowed" {
  command = plan
  variables {
    postgresql = {
      channel = "16/stable"
    }
  }

  expect_failures = [var.postgresql]
}

run "validate_no_pg16_edge_allowed" {
  command = plan
  variables {
    postgresql = {
      channel = "16/edge"
    }
  }

  expect_failures = [var.postgresql]
}

run "validate_no_pg16_beta_allowed" {
  command = plan
  variables {
    postgresql = {
      channel = "16/beta"
    }
  }

  expect_failures = [var.postgresql]
}

run "validate_no_pg16_candidate_allowed" {
  command = plan
  variables {
    postgresql = {
      channel = "16/candidate"
    }
  }

  expect_failures = [var.postgresql]
}
