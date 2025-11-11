
data "juju_model" "test_model" {
  name = var.model_name
}

data "juju_application" "landscape_server_data" {
  name  = "landscape-server"
  model = var.model_name

  depends_on = [terraform_data.wait_for]
}

data "juju_application" "haproxy_data" {
  name  = "haproxy"
  model = var.model_name

  depends_on = [terraform_data.wait_for]
}

data "juju_application" "postgresql_data" {
  name  = "postgresql"
  model = var.model_name

  depends_on = [terraform_data.wait_for]
}

data "juju_application" "rabbitmq_server_data" {
  name  = "rabbitmq-server"
  model = var.model_name

  depends_on = [terraform_data.wait_for]
}

resource "terraform_data" "wait_for" {
  provisioner "local-exec" {
    working_dir = "../.."

    environment = {
      "MODEL_NAME" = var.model_name
    }

    command = <<-EOT
      juju wait-for model $MODEL_NAME --timeout 3600s --query='forEach(units, unit => unit.workload-status == "active")'
    EOT
  }

  depends_on = [data.juju_model.test_model]

}
