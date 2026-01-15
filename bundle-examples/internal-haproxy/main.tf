resource "terraform_data" "wait_for_landscape" {
  provisioner "local-exec" {
    command = <<-EOT
      juju wait-for model $MODEL_NAME --timeout 3600s --query='forEach(units, unit => unit.workload-status == "active")'
      EOT
    environment = {
      MODEL_NAME = var.model_name
    }
  }
}


data "external" "get_juju_model_uuid_by_name" {
  program = ["bash", "${path.module}/get_juju_uuid_by_name.sh"]
  query = {
    model_name = var.model_name
  }
}

data "external" "get_ssh_public_key" {
  program = ["bash", "${path.module}/get_ssh_public_key.sh"]
}

data "juju_model" "charm_build_model" {
  uuid = data.external.get_juju_model_uuid_by_name.result.uuid
}

resource "juju_model" "saas_model" {
  name       = "lbaas"
  depends_on = [terraform_data.wait_for_landscape]
}

locals {
  hostname = "landscape.local"
}

resource "juju_ssh_key" "mykey" {
  model_uuid = juju_model.saas_model.uuid
  payload    = data.external.get_ssh_public_key.result.key
}

resource "juju_application" "haproxy" {
  model_uuid = juju_model.saas_model.uuid

  charm {
    name    = "haproxy"
    channel = "2.8/edge"
  }

  config = {
    "external-hostname" = local.hostname
    "enable-hsts"       = "false"
  }
}

resource "juju_application" "cert" {
  model_uuid = juju_model.saas_model.uuid

  charm {
    name    = "self-signed-certificates"
    channel = "1/stable"
  }
}

resource "juju_integration" "haproxy_certs" {
  model_uuid = juju_model.saas_model.uuid

  application {
    name     = juju_application.haproxy.name
    endpoint = "certificates"
  }

  application {
    name     = juju_application.cert.name
    endpoint = "certificates"
  }
}

resource "juju_offer" "haproxy_route" {
  model_uuid       = juju_model.saas_model.uuid
  application_name = juju_application.haproxy.name
  endpoints        = ["haproxy-route"]
}
