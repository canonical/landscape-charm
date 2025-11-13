# Landscape Server charm Terraform module

This directory contains a base [Terraform][Terraform] module for the [Landscape Server charm][Landscape Server charm].

It uses the [Terraform Juju provider][Terraform Juju provider] to model the charm deployment onto any non-Kubernetes cloud managed by [Juju][Juju].

While it is possible to deploy this module in isolation, it should serve as a building block for higher-level Terraform modules. For example, it's used in the [Landscape Scalable product module][Landscape Scalable Product Module].

## Inputs

The module offers the following configurable inputs:

| Name          | Type        | Description                                                                                                                           | Required | Default            |
| ------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------ |
| `app_name`    | string      | Name of the application in the Juju model                                                                                             | False    | `landscape-server` |
| `base`        | string      | The operating system on which to deploy                                                                                               | False    | `ubuntu@22.04`     |
| `channel`     | string      | The channel to use when deploying the charm                                                                                           | False    | `25.10/edge`       |
| `config`      | map(string) | Application config. The full configuration details for a given revision, base, and channel can be found on [Charmhub][Configurations] | False    | `{}`               |
| `constraints` | string      | Juju constraints to apply for this application                                                                                        | False    | `arch=amd64`       |
| `model`       | string      | The name of a Juju model.                                                                                                             | True     | -                  |
| `revision`    | number      | Revision number of the charm                                                                                                          | False    | `null` (latest)    |
| `units`       | number      | Number of units to deploy                                                                                                             | False    | `1`                |

## Outputs

Upon being applied, the module exports the following outputs:

| Name       | Description                                                                                                                           |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `app_name` | Name of the deployed application                                                                                                      |
| `provides` | Map of integration endpoints this charm provides (`cos-agent`, `data`, `hosted`, `nrpe-external-master`, `website`)                   |
| `requires` | Map of integration endpoints this charm requires (`application-dashboard`, `db`/`database`, `amqp` or `inbound-amqp`/`outbound-amqp`) |

```{note}
The `requires` output dynamically adjusts based on the charm revision and channel:
- AMQP relations: `amqp` (legacy, charm revision ≤ 141 or using specific channels), or `inbound-amqp` and `outbound-amqp` (modern)
- Database relations: `db` only (legacy), or `db` and `database` (modern, charm revision ≥ 210 with a base of `ubuntu@22.04` or ≥ 211 otherwise )
```

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
[Configurations]: https://charmhub.io/landscape-server/configurations
[Integrations]: https://charmhub.io/landscape-server/integrations
[Juju]: https://juju.is
[Terraform]: https://developer.hashicorp.com/terraform
[Terraform Juju provider]: https://registry.terraform.io/providers/juju/juju/latest
