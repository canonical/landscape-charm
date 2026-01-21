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

run "validate_output_structure" {
  command = apply

  assert {
    condition     = output.applications != null
    error_message = "Applications output should exist"
  }

  assert {
    condition     = can(output.applications.landscape_server)
    error_message = "Applications output should include landscape_server"
  }

  assert {
    condition     = can(output.applications.haproxy)
    error_message = "Applications output should include haproxy"
  }

  assert {
    condition     = can(output.applications.postgresql)
    error_message = "Applications output should include postgresql"
  }

  assert {
    condition     = can(output.applications.rabbitmq_server)
    error_message = "Applications output should include rabbitmq_server"
  }
}

run "validate_self_signed_output" {
  command = plan

  assert {
    condition     = output.haproxy_self_signed != null
    error_message = "haproxy_self_signed output should exist"
  }

  assert {
    condition     = output.haproxy_self_signed == true
    error_message = "With default SELFSIGNED ssl_cert, haproxy_self_signed should be true"
  }
}

run "validate_self_signed_false_with_custom_cert" {
  command = plan

  variables {
    haproxy = {
      config = {
        ssl_cert = "custom-cert-content"
        ssl_key  = "custom-key-content"
      }
    }
  }

  assert {
    condition     = output.haproxy_self_signed == false
    error_message = "With custom SSL cert/key, haproxy_self_signed should be false"
  }
}

run "validate_has_modern_amqp_relations_output" {
  command = plan

  assert {
    condition     = output.has_modern_amqp_relations != null
    error_message = "has_modern_amqp_relations output should exist"
  }

  assert {
    condition     = output.has_modern_amqp_relations == local.has_modern_amqp_relations
    error_message = "has_modern_amqp_relations output should match the local value"
  }
}


run "validate_optional_outputs" {
  command = plan

  assert {
    condition     = can(output.registration_key) || output.registration_key == null
    error_message = "registration_key output should be accessible (nullable)"
  }

  assert {
    condition     = can(output.admin_email) || output.admin_email == null
    error_message = "admin_email output should be accessible (nullable)"
  }

  assert {
    condition     = can(output.admin_password) || output.admin_password == null
    error_message = "admin_password output should be accessible (nullable)"
  }
}

run "validate_outputs_with_config" {
  command = plan

  variables {
    landscape_server = {
      revision = 150
      config = {
        registration_key = "test-key-12345"
        admin_email      = "admin@example.com"
        admin_password   = "secure-password"
      }
    }
  }

  assert {
    condition     = output.registration_key == "test-key-12345"
    error_message = "registration_key output should match configured value"
  }

  assert {
    condition     = output.admin_email == "admin@example.com"
    error_message = "admin_email output should match configured value"
  }

  assert {
    condition     = output.admin_password == "secure-password"
    error_message = "admin_password output should match configured value"
  }
}
