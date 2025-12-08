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

When developing the charm, you can use the [`ccc pack`](https://github.com/canonical/charmcraftcache) command to build the charm locally.

> [!NOTE]
> Make sure you add this repository (https://github.com/canonical/landscape-charm) as a remote to your fork, otherwise `ccc` will fail.

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

The Landscape charm integrates with Terraform modules.

### Run tests

Run the Terraform tests:

> [!IMPORTANT]
> Make sure you have `terraform` installed:
>
> ````sh
> sudo snap install terraform --classic
> ````

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
