# Contributing

## Development setup

This project uses [pipx](https://github.com/pypa/pipx) and [poetry](https://python-poetry.org/) for dependency management. Make sure you have both installed:

```sh
sudo apt install -y pipx
pipx install poetry
```

Then, install the project dependencies:

```sh
poetry install --with dev
```

### Run unit tests

```sh
make test
```

Or run specific test(s):

```sh
poetry run pytest tests/unit/test_charm.py::TestCharm::test_install
```

Run with coverage:

```sh
make coverage
```

### Run integration tests

```sh
make integration-test
```

The integration tests can take a while to set up. If you already have an active Juju deployment for a Landscape server bundle that you want to run the integration tests against, you can use it by settting `LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1`:

```sh
LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 make integration-test
```

#### LBaaS integration tests

The LBaaS (Load Balancer as a Service) integration tests verify external HAProxy load balancing functionality with the Landscape Server cahrm. These tests require a separate Juju model with HAProxy deployed.

To set up the LBaaS automatically:

```sh
make lbaas
```

This will deploy the Landscape Server model, create a separate `lbaas` model with HAProxy and the self-signed certificates operator, and then configure cross-model relations between the models. This allows Landscape to be load balanced by the external HAProxy.

> [!IMPORTANT]
> You need an SSH public key to access the Juju models. If you don't have one:
>
> ```sh
> ssh-keygen -t ed25519
> ```

Then, the exisitng models can be used for the integration tests by passing the following environment variables:

```sh
LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 LANDSCAPE_CHARM_USE_HOST_LBAAS_MODEL=1 LBAAS_MODEL_NAME=lbaas make integration-test
```

To access Landscape when being load balanced by the LBaaS, you must include the configured hostname in all requests: `landscape.local` (or the hostname of the `root_url` set in the charm config). For example, to access the Landscape UI in a web browser, add the hostname and the IP address of HAProxy to your `/etc/hosts` file.

### Lint and format code

Run the following to lint the Python code:

```sh
make lint
```

Run the following to format the Python code:

```sh
make fmt
```

### Build the charm

When developing the charm, you can use the [`poetry run ccc pack`](https://github.com/canonical/charmcraftcache) command to build the charm locally.

> [!NOTE]
> Make sure you add this repository (<https://github.com/canonical/landscape-charm>) as a remote to your fork, otherwise `ccc` will fail.

Use the following command to test the charm as it would be deployed by Juju in the `landscape-scalable` bundle:

```bash
make deploy
```

You can also specify the platform to build the charm for, the path to the bundle to deploy, and the name of the model. For example:

```sh
make PLATFORM=ubuntu@24.04:amd64 BUNDLE_PATH=./bundle-examples/postgres16.bundle.yaml MODEL_NAME=landscape-pg16 deploy
```

The cleaning and building steps can be skipped by passing `SKIP_CLEAN=true` and `SKIP_BUILD=true`, respectively. This will create a model called `landscape-pg16`.

## Terraform development

The Landscape charm integrates with Terraform modules for infrastructure provisioning, including LBaaS setup.

### Run tests

Run the Terraform tests:

> [!IMPORTANT]
> Make sure you have `terraform` installed:
>
> ```sh
> make install-terraform
> ```
>
> Or manually install:
>
> ```sh
> sudo snap install terraform --classic
> ```

```sh
make terraform-test
```

### Lint and format

To lint the Terraform module, make sure you have `tflint` installed:

```sh
sudo snap install tflint
```

Then, use the following Make recipe:

```sh
make tflint-fix
```

Format the Terraform module:

```sh
make fmt-fix
```
