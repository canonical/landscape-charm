# © 2025 Canonical Ltd.

mock_provider "juju" {}

run "modern_amqp_relations" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 200
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.inbound_amqp == "inbound-amqp"
    error_message = "Modern revision should use inbound-amqp relation"
  }

  assert {
    condition     = output.requires.outbound_amqp == "outbound-amqp"
    error_message = "Modern revision should use outbound-amqp relation"
  }

  assert {
    condition     = !can(output.requires.amqp)
    error_message = "Modern revision should not have legacy amqp relation"
  }
}

run "legacy_amqp_relations_by_revision" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 141
    base     = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.amqp == "amqp"
    error_message = "Revision 141 should use legacy amqp relation"
  }

  assert {
    condition     = !can(output.requires.inbound_amqp)
    error_message = "Legacy revision should not have inbound-amqp relation"
  }

  assert {
    condition     = !can(output.requires.outbound_amqp)
    error_message = "Legacy revision should not have outbound-amqp relation"
  }
}

run "legacy_amqp_relations_by_channel" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "latest/stable"
    revision = 200
    base     = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.amqp == "amqp"
    error_message = "latest/stable channel should use legacy amqp relation"
  }

  assert {
    condition     = !can(output.requires.inbound_amqp)
    error_message = "Legacy channel should not have inbound-amqp relation"
  }
}

run "modern_postgres_ubuntu_2404" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 211
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Should have db relation"
  }

  assert {
    condition     = output.requires.database == "database"
    error_message = "Modern PostgreSQL interface should have database relation"
  }
}

run "modern_postgres_ubuntu_2204" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 210
    base     = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Should have db relation"
  }

  assert {
    condition     = output.requires.database == "database"
    error_message = "Modern PostgreSQL interface should have database relation"
  }
}

run "legacy_postgres_ubuntu_2404" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 210
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Should have db relation"
  }

  assert {
    condition     = !can(output.requires.database)
    error_message = "Legacy PostgreSQL interface should not have database relation"
  }
}

run "legacy_postgres_ubuntu_2204" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 209
    base     = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Should have db relation"
  }

  assert {
    condition     = !can(output.requires.database)
    error_message = "Legacy PostgreSQL interface should not have database relation"
  }
}

run "unknown_base_defaults" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 211
    base     = "ubuntu@20.04"
  }

  assert {
    condition     = output.requires.db == "db"
    error_message = "Should have db relation"
  }

  assert {
    condition     = output.requires.database == "database"
    error_message = "Unknown base with revision >= 211 should have modern database relation"
  }
}

run "provides_relations" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 200
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.provides.cos_agent == "cos-agent"
    error_message = "Should provide cos-agent relation"
  }

  assert {
    condition     = output.provides.data == "data"
    error_message = "Should provide data relation"
  }

  assert {
    condition     = output.provides.hosted == "hosted"
    error_message = "Should provide hosted relation"
  }

  assert {
    condition     = output.provides.nrpe_external_master == "nrpe-external-master"
    error_message = "Should provide nrpe-external-master relation"
  }

  assert {
    condition     = output.provides.website == "website"
    error_message = "Should provide website relation"
  }
}

run "application_dashboard_required" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "latest/stable"
    revision = 100
    base     = "ubuntu@22.04"
  }

  assert {
    condition     = output.requires.application_dashboard == "application-dashboard"
    error_message = "Should always require application-dashboard relation"
  }
}

run "app_name_output" {
  command = plan

  variables {
    model    = "test-model"
    app_name = "custom-landscape"
    channel  = "25.10/edge"
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.app_name == "custom-landscape"
    error_message = "app_name output should match input variable"
  }
}

run "amqp_threshold_edge_case" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "25.10/edge"
    revision = 142
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.inbound_amqp == "inbound-amqp"
    error_message = "Revision 142 should use modern amqp relations"
  }

  assert {
    condition     = output.requires.outbound_amqp == "outbound-amqp"
    error_message = "Revision 142 should use modern amqp relations"
  }
}

run "legacy_amqp_modern_postgres" {
  command = plan

  variables {
    model    = "test-model"
    channel  = "24.04/edge"
    revision = 211
    base     = "ubuntu@24.04"
  }

  assert {
    condition     = output.requires.amqp == "amqp"
    error_message = "24.04/edge channel should use legacy amqp"
  }

  assert {
    condition     = output.requires.database == "database"
    error_message = "Revision 211 on ubuntu@24.04 should use modern postgres"
  }
}
