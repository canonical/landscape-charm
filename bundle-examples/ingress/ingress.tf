data "juju_model" "landscape_charm_build" {
  uuid = var.model_uuid
}

data "juju_application" "haproxy" {
  model_uuid = var.model_uuid
  name       = "haproxy"
}

data "juju_application" "landscape" {
  model_uuid = var.model_uuid
  name       = "landscape-server"
}

data "external" "landscape_info" {
  program = [
    "bash",
    "-c",
    <<-EOT
    MODEL=$(jq -r '.model_name')
    STATUS=$(juju status -m "$MODEL" --format=json)

    printf '%s' "$STATUS" | jq -c '
      .applications["landscape-server"].units
      | to_entries
      | {
          leader_ip: (
            map(select(.value.leader == true))[0].value["public-address"]
          ),
          machine_id: (
            map(select(.value.leader == true))[0].value.machine
          ),
          all_unit_ips: (
            map(.value["public-address"])
            | join(",")
          )
        }
    '

    EOT
  ]

  query = {
    model_name = data.juju_model.landscape_charm_build.name
  }

  depends_on = [terraform_data.wait_for_landscape]
}

resource "terraform_data" "wait_for_landscape" {
  provisioner "local-exec" {
    command = <<-EOT
    juju wait-for application landscape-server -m $MODEL_NAME --query='(status=="active")'
    EOT

    environment = {
      MODEL_NAME = data.juju_model.landscape_charm_build.name
    }
  }

}



locals {
  appserver_port      = 8080
  pingserver_port     = 8070
  repository_port     = 8060
  message_server_port = 8090
  api_server_port     = 9080
  package_upload_port = 9100

  backend_addresses      = data.external.landscape_info.result.all_unit_ips
  leader_backend_address = data.external.landscape_info.result.leader_ip

  appserver_backend_ports      = join(",", [for i in range(var.twisted_workers) : tostring(local.appserver_port + i)])
  pingserver_backend_ports     = join(",", [for i in range(var.twisted_workers) : tostring(local.pingserver_port + i)])
  message_server_backend_ports = join(",", [for i in range(var.twisted_workers) : tostring(local.message_server_port + i)])
  api_backend_ports            = join(",", [for i in range(var.twisted_workers) : tostring(local.api_server_port + i)])
  package_upload_backend_ports = join(",", [for i in range(var.twisted_workers) : tostring(local.package_upload_port + i)])

  appserver_config = {
    "backend-ports"     = local.appserver_backend_ports
    "backend-addresses" = local.backend_addresses
    "paths"             = "/,/hash-id-databases"
    "hostname"          = var.haproxy_hostname
  }

  pingserver_config = {
    "backend-ports"     = local.pingserver_backend_ports
    "backend-addresses" = local.backend_addresses
    "paths"             = "/ping"
    "hostname"          = var.haproxy_hostname
    "allow-http"        = "true"
  }

  repository_config = {
    "backend-ports"     = local.appserver_backend_ports
    "backend-addresses" = local.backend_addresses
    "paths"             = "/repository"
    "hostname"          = var.haproxy_hostname
    "allow-http"        = "true"
  }

  message_server_config = {
    "backend-ports"     = local.message_server_backend_ports
    "backend-addresses" = local.backend_addresses
    "paths"             = "/message-system,/attachment"
    "hostname"          = var.haproxy_hostname
  }

  api_config = {
    "backend-ports"     = local.api_backend_ports
    "backend-addresses" = local.backend_addresses
    "paths"             = "/api"
    "hostname"          = var.haproxy_hostname
  }

  package_upload_config = {
    "backend-ports"     = local.package_upload_backend_ports
    "backend-addresses" = local.leader_backend_address
    "paths"             = "/upload"
    "hostname"          = var.haproxy_hostname
  }
}

resource "juju_application" "appserver" {
  name = "appserver"

  model_uuid = var.model_uuid

  charm {
    name    = "ingress-configurator"
    channel = "latest/edge"
    base    = "ubuntu@24.04"
  }

  constraints = "arch=amd64"

  config = local.appserver_config

  machines = [data.external.landscape_info.result.machine_id]

  depends_on = [data.external.landscape_info]

}

resource "juju_integration" "appserver_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.appserver.name
    endpoint = "haproxy-route"
  }

  application {
    name = data.juju_application.haproxy.name
  }

  depends_on = [juju_integration.api_haproxy, juju_integration.pingserver_haproxy, juju_integration.message_server_haproxy, juju_integration.package_upload_haproxy, juju_integration.repository_haproxy]
}

resource "juju_application" "pingserver" {
  name = "pingserver"

  model_uuid = var.model_uuid

  charm {
    name    = "ingress-configurator"
    channel = "latest/edge"
    base    = "ubuntu@24.04"
  }

  constraints = "arch=amd64"

  config = local.pingserver_config

  machines = [data.external.landscape_info.result.machine_id]
}

resource "juju_integration" "pingserver_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.pingserver.name
    endpoint = "haproxy-route"
  }

  application {
    name = data.juju_application.haproxy.name
  }
}

resource "juju_application" "api" {
  name = "api"

  model_uuid = var.model_uuid

  charm {
    name    = "ingress-configurator"
    channel = "latest/edge"
    base    = "ubuntu@24.04"
  }

  constraints = "arch=amd64"

  config = local.api_config

  machines = [data.external.landscape_info.result.machine_id]

  depends_on = [data.external.landscape_info]
}

resource "juju_integration" "api_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.api.name
    endpoint = "haproxy-route"
  }

  application {
    name = data.juju_application.haproxy.name
  }
}

resource "juju_application" "repository" {
  name = "repository"

  model_uuid = var.model_uuid

  charm {
    name    = "ingress-configurator"
    channel = "latest/edge"
    base    = "ubuntu@24.04"
  }

  config = local.repository_config

  constraints = "arch=amd64"

  machines = [data.external.landscape_info.result.machine_id]

  depends_on = [data.external.landscape_info]
}

resource "juju_integration" "repository_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.repository.name
    endpoint = "haproxy-route"
  }

  application {
    name = data.juju_application.haproxy.name
  }
}

resource "juju_application" "message_server" {
  name = "message-server"

  model_uuid = var.model_uuid

  charm {
    name    = "ingress-configurator"
    channel = "latest/edge"
    base    = "ubuntu@24.04"
  }

  constraints = "arch=amd64"

  config = local.message_server_config

  machines = [data.external.landscape_info.result.machine_id]

  depends_on = [data.external.landscape_info]

}

resource "juju_integration" "message_server_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.message_server.name
    endpoint = "haproxy-route"
  }

  application {
    name = data.juju_application.haproxy.name
  }
}

resource "juju_application" "package_upload" {
  name = "package-upload"

  model_uuid = var.model_uuid

  charm {
    name    = "ingress-configurator"
    channel = "latest/edge"
    base    = "ubuntu@24.04"
  }

  config = local.package_upload_config

  constraints = "arch=amd64"

  machines = [data.external.landscape_info.result.machine_id]

  depends_on = [data.external.landscape_info]
}

resource "juju_integration" "package_upload_haproxy" {
  model_uuid = var.model_uuid

  application {
    name     = juju_application.package_upload.name
    endpoint = "haproxy-route"
  }

  application {
    name = data.juju_application.haproxy.name
  }
}
