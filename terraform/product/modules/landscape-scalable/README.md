# Landscape Scalable Product Module

> [!CAUTION]
> This module is not currently compatible with Charmed PostgreSQL 16. You cannot use the `16/stable`, `16/candidate`, `16/edge`, or `16/beta` channels of the `postgresql` charm.

This module requires a bootstrapped Juju cloud with a model created within it, the name of which can be provided as `model`.

For example, bootstrap a LXD cloud:

```sh
juju bootstrap lxd landscape-controller
```

Then, create a model named `landscape`:

```sh
juju add-model landscape
```

Then, use `landscape` as the value for `model`:

```sh
terraform apply -var model=landscape
```

After deploying the module to the model, use the `juju status` command to monitor the lifecycle:

```sh
juju status -m landscape --relations --watch 2s
```

> [!TIP]
> Customize the module inputs with a `terraform.tfvars` file. An example is `terraform.tfvars.example`, which can be used after removing the `.example` extension.

This module uses the [Landscape Server charm module](https://github.com/canonical/landscape-charm/tree/main/terraform).

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

| Name | Source | Version |
|------|--------|---------|
| <a name="module_haproxy"></a> [haproxy](#module\_haproxy) | git::https://github.com/canonical/haproxy-operator.git//terraform/charm | rev250 |
| <a name="module_landscape_server"></a> [landscape\_server](#module\_landscape\_server) | git::https://github.com/jansdhillon/landscape-charm.git//terraform | update-tf-module |
| <a name="module_postgresql"></a> [postgresql](#module\_postgresql) | git::https://github.com/canonical/postgresql-operator.git//terraform | rev935 |

## Resources

| Name | Type |
|------|------|
| [juju_application.rabbitmq_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/application) | resource |
| [juju_integration.landscape_server_haproxy](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_inbound_amqp](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_outbound_amqp](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_postgresql](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |
| [juju_integration.landscape_server_rabbitmq_server](https://registry.terraform.io/providers/juju/juju/latest/docs/resources/integration) | resource |

## Inputs

| Name | Description | Type | Default | Required |
|------|-------------|------|---------|:--------:|
| <a name="input_haproxy"></a> [haproxy](#input\_haproxy) | Configuration for the HAProxy charm. | <pre>object({<br/>    app_name = optional(string, "haproxy")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      default_timeouts            = "queue 60000, connect 5000, client 120000, server 120000"<br/>      global_default_bind_options = "no-tlsv10"<br/>      services                    = ""<br/>      ssl_cert                    = "SELFSIGNED"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@22.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_landscape_server"></a> [landscape\_server](#input\_landscape\_server) | Configuration for the Landscape Server charm. | <pre>object({<br/>    app_name = optional(string, "landscape-server")<br/>    channel  = optional(string, "25.10/beta")<br/>    config = optional(map(string), {<br/>      autoregistration = "true"<br/>      landscape_ppa    = "ppa:landscape/self-hosted-beta"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@22.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_model"></a> [model](#input\_model) | The name of the Juju model to deploy Landscape Server to. | `string` | n/a | yes |
| <a name="input_postgresql"></a> [postgresql](#input\_postgresql) | Configuration for the PostgreSQL charm. | <pre>object({<br/>    app_name = optional(string, "postgresql")<br/>    channel  = optional(string, "14/stable")<br/>    config = optional(map(string), {<br/>      plugin_plpython3u_enable     = "true"<br/>      plugin_ltree_enable          = "true"<br/>      plugin_intarray_enable       = "true"<br/>      plugin_debversion_enable     = "true"<br/>      plugin_pg_trgm_enable        = "true"<br/>      experimental_max_connections = "500"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@22.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |
| <a name="input_rabbitmq_server"></a> [rabbitmq\_server](#input\_rabbitmq\_server) | Configuration for the RabbitMQ charm. | <pre>object({<br/>    app_name = optional(string, "rabbitmq-server")<br/>    channel  = optional(string, "latest/edge")<br/>    config = optional(map(string), {<br/>      consumer-timeout = "259200000"<br/>    })<br/>    constraints = optional(string, "arch=amd64")<br/>    resources   = optional(map(string), {})<br/>    revision    = optional(number)<br/>    base        = optional(string, "ubuntu@24.04")<br/>    units       = optional(number, 1)<br/>  })</pre> | `{}` | no |

## Outputs

| Name | Description |
|------|-------------|
| <a name="output_admin_email"></a> [admin\_email](#output\_admin\_email) | Administrator email from the Landscape Server config. |
| <a name="output_admin_password"></a> [admin\_password](#output\_admin\_password) | Administrator password from the Landscape Server config (sensitive). |
| <a name="output_applications"></a> [applications](#output\_applications) | The charms included in the module. |
| <a name="output_haproxy_self_signed"></a> [haproxy\_self\_signed](#output\_haproxy\_self\_signed) | Indicates whether HAProxy is using a self-signed TLS certificate. |
| <a name="output_has_modern_amqp_relations"></a> [has\_modern\_amqp\_relations](#output\_has\_modern\_amqp\_relations) | Indicates whether the deployment uses the modern inbound/outbound AMQP endpoints. |
| <a name="output_registration_key"></a> [registration\_key](#output\_registration\_key) | Registration key from the Landscape Server config. |
<!-- END_TF_DOCS -->
