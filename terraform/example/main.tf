
resource "juju_model" "test_model" {
  name = var.model_name
}

module "landscape_server" {
  source     = "../."
  model_uuid = juju_model.test_model.uuid

  depends_on = [juju_model.test_model]
}

resource "terraform_data" "refresh_local_charm" {
  provisioner "local-exec" {
    working_dir = "../.."

    environment = {
      "MODEL_NAME" = var.model_name
      "APP_NAME"   = var.app_name
    }

    command = <<-EOT
        juju refresh -m $MODEL_NAME $APP_NAME --path=./landscape-server_${replace(var.platform, ":", "-")}.charm
    EOT
  }

  depends_on = [module.landscape_server]
}
