
resource "juju_model" "test_model" {
  name = var.model_name
}

module "landscape_server" {
  source     = "git::https://github.com/canonical/terraform-juju-landscape-server.git//modules/landscape-scalable?ref=v1.0.3"
  model_uuid = juju_model.test_model.uuid

  depends_on = [juju_model.test_model]
}

resource "terraform_data" "refresh_local_charm" {
  provisioner "local-exec" {
    working_dir = "../.."

    environment = {
      "MODEL_NAME" = var.model_name
    }

    command = <<-EOT
        juju wait-for application landscape-server -m $MODEL_NAME --query='status=="active"' && \
          juju refresh -m $MODEL_NAME landscape-server --path=./landscape-server_${replace(var.platform, ":", "-")}.charm
    EOT
  }

  depends_on = [module.landscape_server]
}
