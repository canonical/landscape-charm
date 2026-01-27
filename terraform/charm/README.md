# Landscape Server Charm Module

> [!CAUTION]
> This module is not currently compatible with Charmed PostgreSQL 16. You cannot relate it to the `16/stable`, `16/candidate`, `16/edge`, or `16/beta` channels of the `postgresql` charm.

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

## Contributing

The Landscape charm integrates with Terraform modules.

Make sure you have `terraform` installed:

>
````sh
sudo snap install terraform --classic
````

### Run tests

Run the Terraform tests:

```sh
make test-charm-module
```

### Lint and format

To lint the Terraform module, make sure you have `tflint` installed:

```sh
sudo snap install tflint
```

Then, use the following Make recipe:

```sh
make fix-charm-module
```

[Landscape Server charm]: https://charmhub.io/landscape-server
[Landscape Scalable Product Module]: ../product
[Integrations]: https://charmhub.io/landscape-server/integrations
[Juju]: https://juju.is
[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest

<!-- BEGIN_TF_DOCS -->
## Requirements

| Name | Version |
|------|---------|
| <a name="requirement_terraform"></a> [terraform](#requirement\_terraform) | >= 1.10 |
| <a name="requirement_juju"></a> [juju](#requirement\_juju) | < 1.0.0 |

## Providers

| Name | Version |
|------|---------|
| <a name="provider_juju"></a> [juju](#provider\_juju) | < 1.0.0 |

## Modules

No modules.

## Resources

| Name | Type |
|------|------|
| [juju_application.landscape_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_app_name"></a> [app\_name](#input\_app\_name) | Name of the application in the Juju model. | `string` | `"landscape-server"` | no |
| <a name="input_base"></a> [base](#input\_base) | The operating system on which to deploy. | `string` | `"ubuntu@22.04"` | no |
| <a name="input_channel"></a> [channel](#input\_channel) | The channel to use when deploying a charm. | `string` | `"latest-stable/edge"` | no |
| <a name="input_config"></a> [config](#input\_config) | Application config. Details about available options can be found at https://charmhub.io/landscape-server/configurations. | `map(string)` | `{}` | no |
| <a name="input_constraints"></a> [constraints](#input\_constraints) | Juju constraints to apply for this application. | `string` | `"arch=amd64"` | no |
| <a name="input_model"></a> [model](#input\_model) | Reference to a `juju_model`. | `string` | n/a | yes |
| <a name="input_revision"></a> [revision](#input\_revision) | Revision number of the charm. | `number` | `null` | no |
| <a name="input_units"></a> [units](#input\_units) | Number of units to deploy. | `number` | `1` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_app_name"></a> [app\_name](#output\_app\_name) | Name of the deployed application. |
| <a name="output_provides"></a> [provides](#output\_provides) | Map of integration endpoints this charm provides (`cos-agent`, `data`, `hosted`, `nrpe-external-master`, `website`). |
| <a name="output_requires"></a> [requires](#output\_requires) | Map of integration endpoints this charm requires (`application-dashboard`, `db`, `amqp` or `inbound-amqp`/`outbound-amqp`). |
<!-- END_TF_DOCS -->
