
data "juju_model" "test_model" {
  name = var.model_name
}

data "juju_application" "landscape_server_data" {
  name  = "landscape-server"
  model = var.model_name

  depends_on = [terraform_data.refresh_local_charm]
}

data "juju_application" "haproxy_data" {
  name  = "haproxy"
  model = var.model_name

  depends_on = [terraform_data.refresh_local_charm]
}

data "juju_application" "postgresql_data" {
  name  = "postgresql"
  model = var.model_name

  depends_on = [terraform_data.refresh_local_charm]
}

data "juju_application" "rabbitmq_server_data" {
  name  = "rabbitmq_server"
  model = var.model_name

  depends_on = [terraform_data.refresh_local_charm]
}

locals {
  base = split(":", var.platform)[0]
}

resource "terraform_data" "refresh_local_charm" {
  provisioner "local-exec" {
    working_dir = "../.."

    environment = {
      "MODEL_NAME" = var.model_name
    }

    command = <<-EOT
    juju wait-for model $MODEL_NAME --timeout 3600s --query='forEach(units, unit => unit.workload-status == "active")' && \
      juju refresh -m $MODEL_NAME landscape-server --path=./landscape-server_${replace(var.platform, ":", "-")}.charm
    EOT
  }

  depends_on = [data.juju_model.test_model]

}
