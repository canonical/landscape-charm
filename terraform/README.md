# Landscape Server Charm Module

This directory contains a base [Terraform][Terraform] module for the [Landscape Server charm][Landscape Server charm].

It uses the [Terraform Juju provider][Terraform Juju provider] to model the charm deployment onto any non-Kubernetes cloud managed by [Juju][Juju].

While it is possible to deploy this module in isolation, it should serve as a building block for higher-level Terraform modules. For example, it's used in the [Landscape Scalable product module][Landscape Scalable Product Module].

## Using the module in higher level modules

To use this in your Terraform module, import it like this:

```hcl
data "juju_model" "my_model" {
  name = var.model
}

module "landscape_server" {
  source = "git::https://github.com/canonical/landscape-charm//terraform"

  model = juju_model.my_model.name
  # Customize configuration variables here if needed, for example:
  # config = {
  #   min_install = true
  # }
}
```

Then, create integrations, for example:

```hcl
resource "juju_integration" "landscape_server_haproxy" {
  model = juju_model.my_model.name

  application {
    name     = module.haproxy.app_name
    endpoint = module.haproxy.requires.reverseproxy
  }

  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.provides.website
  }
}
```

The complete list of available integrations can be found on [Charmhub][Integrations].

[Landscape Server charm]: https://charmhub.io/landscape-server
[Landscape Scalable Product Module]: https://github.com/canonical/terraform-juju-landscape/blob/main/modules/landscape-scalable
[Integrations]: https://charmhub.io/landscape-server/integrations
[Juju]: https://juju.is
[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest

<!-- BEGIN_TF_DOCS -->

## Requirements

| Name                                                                     | Version |
| ------------------------------------------------------------------------ | ------- |
| <a name="requirement_terraform"></a> [terraform](#requirement_terraform) | >= 1.10 |
| <a name="requirement_juju"></a> [juju](#requirement_juju)                | < 1.0.0 |

## Providers

| Name                                                | Version |
| --------------------------------------------------- | ------- |
| <a name="provider_juju"></a> [juju](#provider_juju) | < 1.0.0 |

## Modules

No modules.

## Resources

| Name                                                                                                                     | Type     |
| ------------------------------------------------------------------------------------------------------------------------ | -------- |
| [juju_application.landscape_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |

## Inputs

| Name                                                               | Description                                                                                                              | Type          | Default              | Required |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ | ------------- | -------------------- | :------: |
| <a name="input_app_name"></a> [app_name](#input_app_name)          | Name of the application in the Juju model.                                                                               | `string`      | `"landscape-server"` |    no    |
| <a name="input_base"></a> [base](#input_base)                      | The operating system on which to deploy.                                                                                 | `string`      | `"ubuntu@22.04"`     |    no    |
| <a name="input_channel"></a> [channel](#input_channel)             | The channel to use when deploying a charm.                                                                               | `string`      | `"25.10/edge"`       |    no    |
| <a name="input_config"></a> [config](#input_config)                | Application config. Details about available options can be found at https://charmhub.io/landscape-server/configurations. | `map(string)` | `{}`                 |    no    |
| <a name="input_constraints"></a> [constraints](#input_constraints) | Juju constraints to apply for this application.                                                                          | `string`      | `"arch=amd64"`       |    no    |
| <a name="input_model"></a> [model](#input_model)                   | Reference to a `juju_model`.                                                                                             | `string`      | n/a                  |   yes    |
| <a name="input_revision"></a> [revision](#input_revision)          | Revision number of the charm.                                                                                            | `number`      | `null`               |    no    |
| <a name="input_units"></a> [units](#input_units)                   | Number of units to deploy.                                                                                               | `number`      | `1`                  |    no    |

## Outputs

| Name                                                        | Description                                                                                                                            |
| ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| <a name="output_app_name"></a> [app_name](#output_app_name) | Name of the deployed application.                                                                                                      |
| <a name="output_provides"></a> [provides](#output_provides) | Map of integration endpoints this charm provides (`cos-agent`, `data`, `hosted`, `nrpe-external-master`, `website`).                   |
| <a name="output_requires"></a> [requires](#output_requires) | Map of integration endpoints this charm requires (`application-dashboard`, `db`/`database`, `amqp` or `inbound-amqp`/`outbound-amqp`). |

<!-- END_TF_DOCS -->
