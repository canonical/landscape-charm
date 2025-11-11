
resource "juju_model" "test_model" {
  name = var.model_name
}

locals {
  base = split(":", var.platform)[0]
}


module "landscape_server" {
  source = "git::https://github.com/jansdhillon/terraform-juju-landscape-server.git//modules/landscape-scalable?ref=update-pg-interface"
  model  = juju_model.test_model.name

  landscape_server = {
    revision = 212
    base     = local.base
  }
  postgresql = {
    channel  = "16/stable"
    base     = "ubuntu@24.04"
  }
  haproxy         = {}
  rabbitmq_server = {}

  depends_on = [juju_model.test_model]
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

  depends_on = [module.landscape_server]
}
