data "juju_model" "landscape_model" {
  name = var.model_name
}

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

locals {
  ssh_key_files = [
    "~/.ssh/id_ed25519.pub",
    "~/.ssh/id_rsa.pub",
    "~/.ssh/id_ecdsa.pub",
  ]
  ssh_key_path    = coalesce([for f in local.ssh_key_files : f if fileexists(pathexpand(f))]...)
  ssh_key_content = trimspace(file(pathexpand(local.ssh_key_path)))
}

resource "juju_model" "lbaas_model" {
  name = var.lbaas_model_name
}

resource "juju_ssh_key" "lbaas_ssh_key" {
  model   = juju_model.lbaas_model.name
  payload = local.ssh_key_content
}


resource "juju_application" "haproxy" {
  model = juju_model.lbaas_model.name
  name  = "haproxy"

  charm {
    name    = "haproxy"
    channel = "2.8/edge"
  }

  config = {
    external-hostname = "landscape.local"
    enable-hsts       = "false"
  }

  units = 1
}

resource "juju_application" "self_signed_certificates" {
  model = juju_model.lbaas_model.name
  name  = "self-signed-certificates"

  charm {
    name    = "self-signed-certificates"
    channel = "1/stable"
  }

  units = 1
}

resource "juju_integration" "haproxy_certs" {
  model = juju_model.lbaas_model.name

  application {
    name     = juju_application.haproxy.name
    endpoint = "certificates"
  }

  application {
    name     = juju_application.self_signed_certificates.name
    endpoint = "certificates"
  }
}

resource "juju_integration" "haproxy_receive_ca_certs" {
  model = juju_model.lbaas_model.name

  application {
    name     = juju_application.haproxy.name
    endpoint = "receive-ca-certs"
  }

  application {
    name     = juju_application.self_signed_certificates.name
    endpoint = "send-ca-cert"
  }
}

resource "juju_offer" "haproxy_route" {
  model            = juju_model.lbaas_model.name
  application_name = juju_application.haproxy.name
  endpoint         = "haproxy-route"
}

data "juju_offer" "haproxy_route" {
  url = juju_offer.haproxy_route.url
}

resource "juju_integration" "http_ingress" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "http-ingress"
    endpoint = "haproxy-route"
  }
}

resource "juju_integration" "hostagent_messenger_ingress" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "hostagent-messenger-ingress"
    endpoint = "haproxy-route"
  }
}

resource "juju_integration" "ubuntu_installer_attach_ingress" {
  model = data.juju_model.landscape_model.name

  application {
    offer_url = data.juju_offer.haproxy_route.url
  }

  application {
    name     = "ubuntu-installer-attach-ingress"
    endpoint = "haproxy-route"
  }
}

resource "terraform_data" "wait_for_lbaas" {
  provisioner "local-exec" {
    command = <<-EOT
      juju wait-for model $MODEL_NAME --timeout 3600s --query='forEach(units, unit => unit.workload-status == "active")'
      EOT
    environment = {
      MODEL_NAME = var.lbaas_model_name
    }
  }

  depends_on = [juju_offer.haproxy_route, juju_integration.haproxy_certs, juju_integration.haproxy_receive_ca_certs]
}
