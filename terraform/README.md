# Landscape Server charm Terraform module

This folder contains a base [Terraform][Terraform] module for the [Landscape Server charm][Charm].

The module uses the [Terraform Juju provider][Terraform Juju provider] to model the charm
deployment onto any machine cloud environment managed by [Juju][Juju].

The base module is not intended to be deployed in separation (it is possible though), but should
rather serve as a building block for higher level modules.

## Module structure

- **main.tf** - Defines the Juju application to be deployed.
- **variables.tf** - Allows customization of the deployment. Except for exposing the deployment
  options (Juju model name, channel or application name) also models the charm configuration.
- **output.tf** - Responsible for integrating the module with other Terraform modules, primarily
  by defining potential integration endpoints (charm integrations), but also by exposing
  the application name.
- **versions.tf** - Defines the Terraform provider version.
- **locals.tf** - Values computed at deploy time based on the variables provided.

## Using the landscape-server base module in higher level modules

If you want to use `landscape-server` base module as part of your Terraform module, import it
like shown below:

```hcl
data "juju_model" "my_model" {
  name = var.model
}

module "landscape_server" {
  source = "git::https://github.com/canonical/landscape-charm//terraform"
  
  model = juju_model.my_model.name
  # Customize configuration variables here if needed
}
```

Create integrations, for instance:

```hcl
resource "juju_integration" "landscape_server_haproxy" {
  model = juju_model.my_model.name
  application {
    name     = module.landscape_server.app_name
    endpoint = module.landscape_server.requires.website
  }

  application {
    name     = module.haproxy.app_name
    endpoint = module.haproxy.provides.website
  }
}
```

The complete list of available integrations can be found on [Charmhub][integrations].

[Charm]: https://charmhub.io/landscape-server?channel=latest-stable/edge
[Integrations]: https://charmhub.io/landscape-server/integrations?channel=latest-stable/edge
[Juju]: https://juju.is
[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
