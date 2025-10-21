# Landscape Server

## Description

The Landscape systems management tool helps you monitor, manage, and
update your entire Ubuntu infrastructure from a single interface. Part
of Canonical's [Ubuntu Pro](https://ubuntu.com/pro) support service,
Landscape brings you intuitive systems management tools combined with
world-class support.

This charm will deploy Self-Hosted Landscape and needs to be connected
to other charms to be fully functional. Example deployments are given
below.

See the full [Landscape documentation](https://ubuntu.com/landscape/docs)
for more details.

## Usage

Typically, Landscape deployment is done using a Juju bundle. This charm
is not useful without a deployed bundle of services.

Please use one of the following bundle types, depending on your needs:

- [landscape-scalable](https://charmhub.io/landscape-scalable)
- [landscape-dense-maas](https://charmhub.io/landscape-dense-maas)
- [landscape-dense](https://charmhub.io/landscape-dense)

## Relations

See `metadata.yaml` for required and provided relations.

## Configuration

Landscape requires configuration of a license file before deployment.
Please sign in to your "SaaS account" at
[https://landscape.canonical.com](https://landscape.canonical.com) to
download your license file. It can be found by following the link on
the left side of the page: "access the Landscape On Premises archive."

### license-file

You can set this as a juju configuration option after deployment on each
deployed landscape-server application:

```bash
juju config landscape-server "license_file=$(cat license-file)"
```

### SSL

The pre-packaged bundles will ask the HAProxy charm to generate a
self-signed certificate. While useful for testing, this must not be used
for production deployments.

For production deployments, you should include a "real" SSL certificate
key pair (that has been signed by a Certificate Authority that your
clients trust) in the HAproxy service configuration (or in the
landscape-server service configuration if you need to use your HAProxy
service for other services that have different certificates).

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines
on enhancements to this charm following best practice guidelines, and
`CONTRIBUTING.md` for developer guidance.

When developing the charm, here's a quick way to test out changes as
they would be deployed by `landscape-scalable`:

```bash
make build
```

### Run unit tests

```sh
tox -e unit
```

Or run specific test(s):

```sh
tox -e unit -- tests/test_charm.py::TestCharm::test_install
```

### Run integration tests

```sh
tox -e integration
```

The integration tests can take a while to set up. If you already have an active Juju deployment for a Landscape server bundle that you want to run the integration tests against, you can use it by settting `LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1`:

```sh
LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL=1 tox -e integration
```

### Lint code

```sh
tox -e lint
```

### Format code

```sh
tox -e fmt
```
