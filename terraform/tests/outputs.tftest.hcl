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

run "modern_amqp_relations_null_revision" {
  command = plan

  variables {
    model    = "test-model"
    revision = null
  }

  assert {
    condition     = !can(output.requires.amqp)
    error_message = "Null revision should not use legacy amqp relation"
  }

  assert {
    condition     = can(output.requires.inbound_amqp)
    error_message = "Null revision should have inbound-amqp relation"
  }

  assert {
    condition     = can(output.requires.outbound_amqp)
    error_message = "Null revision should have outbound-amqp relation"
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
    error_message = "Legacy channel should use legacy amqp relation"
  }

  assert {
    condition     = !can(output.requires.inbound_amqp)
    error_message = "Legacy channel should not have inbound-amqp relation"
  }

  assert {
    condition     = !can(output.requires.outbound_amqp)
    error_message = "Legacy channel should not have outbound-amqp relation"
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
