# Landscape Server charm Terraform module

This directory contains a base [Terraform][Terraform] module for the [Landscape Server charm][Landscape Server charm].

It uses the [Terraform Juju provider][Terraform Juju provider] to model the charm deployment onto any non-Kubernetes cloud managed by [Juju][Juju].

While it is possible to deploy this module in isolation, it should serve as a building block for higher-level Terraform modules.

## Module structure

- **main.tf** - Defines the Juju application to be deployed.
- **variables.tf** - Provides customizable deployment inputs. This includes options such as the Juju model name, channel, and application name, as well as charm-specific configuration parameters.
- **output.tf** - Exposes values needed by other Terraform modules, such as the application name and integration endpoints (e.g., charm relations).
- **versions.tf** - Defines the required Terraform and provider versions.
- **locals.tf** - Values computed at deploy time based on the variables provided.

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

The complete list of available integrations can be found on [Charmhub][integrations].

[Landscape Server charm]: https://charmhub.io/landscape-server?channel=latest-stable/edge
[Integrations]: https://charmhub.io/landscape-server/integrations?channel=latest-stable/edge
[Juju]: https://juju.is
[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
