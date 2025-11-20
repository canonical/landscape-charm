# Landscape Server

## Description

The Landscape systems management tool helps you monitor, manage, and update your entire Ubuntu infrastructure from a single interface. Part of Canonical's [Ubuntu Pro](https://ubuntu.com/pro) support service, Landscape brings you intuitive systems management tools combined with world-class support.

This charm will deploy Self-Hosted Landscape and needs to be connected to other charms to be fully functional. Example deployments are given below.

See the full [Landscape documentation](https://ubuntu.com/landscape/docs) for more details.

## Usage

Typically, Landscape deployment is done using a Juju bundle. This charm is not useful without a deployed bundle of services. The [landscape-scalable](https://charmhub.io/landscape-scalable) bundle is the recommended setup.

## Relations

See `metadata.yaml` for required and provided relations.

## Configuration

Landscape requires configuration of a license file before deployment. Please sign in to your Landscape SaaS account at [https://landscape.canonical.com](https://landscape.canonical.com) to download your license file. It can be found by following the link on the left side of the page: **To use Self-hosted Landscape download your license file.**

### license-file

You can set this as a juju configuration option after deployment on each deployed landscape-server application:

```bash
juju config landscape-server "license_file=$(cat license-file)"
```

### SSL

The pre-packaged bundles will ask the HAProxy charm to generate a self-signed certificate. While useful for testing, this must not be used for production deployments.

For production deployments, you should include an SSL certificate/key pair that has been signed by a certificate authority that your client devices trust. This may be set in either the HAProxy service configuration or the Landscape server configuration.

To set this configuration in Landscape server:

```sh
juju config landscape-server ssl_key=<SSL_KEY> ssl_cert=<SSL_CERT>
```

The `ssl_key` and `ssl_cert` must be base64-encoded.

## Contributing

Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this charm following best practice guidelines, and `CONTRIBUTING.md` for developer guidance.
