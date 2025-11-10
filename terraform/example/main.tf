
locals {
  create_model  = var.model_name == null
  resolved_name = local.create_model ? var.new_model_name : var.model_name
  model_uuid    = local.create_model ? juju_model.test_model[0].uuid : data.juju_model.test_model[0].uuid
}

resource "juju_model" "test_model" {
  name = var.new_model_name

  count = local.create_model ? 1 : 0
}

data "juju_model" "test_model" {
  name  = var.model_name
  owner = var.model_owner

  count = local.create_model ? 0 : 1
}

module "landscape_server_charm" {
  source     = "../."
  model_uuid = local.model_uuid

  depends_on = [juju_model.test_model, data.juju_model.test_model]
}


resource "terraform_data" "build_charm" {
  provisioner "local-exec" {
    working_dir = "../.."

    command = <<-EOT
        make build PLATFORM=${var.platform}
    EOT
  }

  depends_on = [module.landscape_server_charm]
}

resource "terraform_data" "deploy_local_charm" {
  provisioner "local-exec" {
    working_dir = "../.."

    environment = {
      "MODEL_NAME" = local.resolved_name
    }

    command = <<-EOT
        juju remove-application -m $MODEL_NAME --no-prompt landscape-server --force --no-wait
        juju deploy -m $MODEL_NAME "./landscape-server_${replace(var.platform, ":", "-")}.charm"
    EOT
  }

  depends_on = [terraform_data.build_charm]
}
