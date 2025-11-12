# Landscape Server charm Terraform module

This directory contains a base [Terraform][Terraform] module for the [Landscape Server charm][Landscape Server charm].

It uses the [Terraform Juju provider][Terraform Juju provider] to model the charm deployment onto any non-Kubernetes cloud managed by [Juju][Juju].

While it is possible to deploy this module in isolation, it should serve as a building block for higher-level Terraform modules.

## API

### Inputs

The module offers the following configurable inputs:

| Name | Type | Description | Required | Default |
| - | - | - | - | - |
| `app_name` | string | Name of the application in the Juju model | False | `landscape-server` |
| `base` | string | The operating system on which to deploy | False | `ubuntu@22.04` |
| `channel` | string | The channel to use when deploying the charm | False | `25.10/edge` |
| `config` | map(string) | Application config. Details at [Charmhub][configurations] | False | `{}` |
| `constraints` | string | Juju constraints to apply for this application | False | `arch=amd64` |
| `model` | string | Reference to a `juju_model` | True | - |
| `revision` | number | Revision number of the charm | False | `null` (latest) |
| `units` | number | Number of units to deploy | False | `1` |

### Outputs

Upon being applied, the module exports the following outputs:

| Name | Description |
| - | - |
| `app_name` | Name of the deployed application |
| `provides` | Map of integration endpoints this charm provides (cos-agent, data, hosted, nrpe-external-master, website) |
| `requires` | Map of integration endpoints this charm requires (application-dashboard, db/database, amqp/inbound-amqp/outbound-amqp) |

> [!NOTE]
> The `requires` output dynamically adjusts based on the charm revision and channel:
>
> - AMQP relations: `amqp` (legacy, ≤ rev 141 or specific channels) or `inbound-amqp` + `outbound-amqp` (modern)
> - Database relations: `db` only (legacy) or `db` + `database` (modern, rev ≥ 210 for ubuntu@22.04, ≥ 211 for ubuntu@24.04)

## Module structure

- **main.tf** - Defines the Juju application to be deployed.
- **variables.tf** - Provides customizable deployment inputs. This includes options such as the Juju model name, channel, and application name, as well as charm-specific configuration parameters.
- **output.tf** - Exposes values needed by other Terraform modules, such as the application name and integration endpoints (e.g., charm relations).
- **versions.tf** - Defines the required Terraform and provider versions.

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

[Landscape Server charm]: https://charmhub.io/landscape-server
[configurations]: https://charmhub.io/landscape-server/configurations
[Integrations]: https://charmhub.io/landscape-server/integrations
[Juju]: https://juju.is
[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
