Overview
========

The Landscape systems management tool helps you monitor, manage and update your
entire Ubuntu infrastructure from a single interface. Part of Canonical’s
Ubuntu Advantage support service, Landscape brings you intuitive systems
management tools combined with world-class support.

This charm will deploy the dedicated version of Landsacpe (LDS), and needs to be
connected to other charms to be fully functional.  Example deployments are given
below.

For more information about Landscape, please visit
[Canonical's website](http://canonical.com/landscape).

Usage
=====

The typical deployment of landscape is as follows:

Configuration
-------------

Landscape will not run without external configuration.  The following
options represent the basic options needed to get landscape up and going.
You can find the PPA and license information in the landscape GUI.  Look on
the left side for "Landscape Dedicated Server" after Canonical Support
has enabled the feature on your account.

    $ cat >lds.cfg <<EOF
        landscape:
            repository: https://user:pass@ppa-server/ppa-path/
            license-file: |
                <license file here>
            services: static appserver msgserver pingserver combo-loader
                      async-frontend apiserver package-upload jobhandler
                      package-search
        postgresql:
            extra-packages: python-apt postgresql-contrib postgresql-9.1-debversion
        apache2:
            enable-modules: proxy proxy_http proxy_balancer rewrite expires headers ssl
            ssl_cert: SELFSIGNED
            ssl_certlocation: apache2.cert
            vhost_https_template: <base64 encoded template>
            vhost_http_template: <base64 encoded template>
        haproxy:
            default_timeouts: queue 60000, connect 5000, client 120000, server 120000
            monitoring_allowed_cidr: 0.0.0.0/0
            monitoring_password: haproxy
            default_timeouts: queue 60000, connect 5000, client 120000, server 120000
    EOF

Deployment
----------

Once configured, you can deploy with the following commands:

    $ juju deploy --config=lds.cfg landscape
    $ juju deploy --config=lds.cfg postgresql
    $ juju deploy --config=lds.cfg apache2
    $ juju deploy haproxy
    $ juju deploy rabbitmq-server
    $ juju add-relation landscape:db-admin postgresql:db-admin
    $ juju add-relation landscape rabbitmq-server
    $ juju add-relation landscape haproxy
    $ juju add-relation haproxy:website apache2:reverseproxy

This will result in a landscape cluster of 5 nodes.  Landscape, postgresql
(database), rabbitmq (message server), haproxy (load balancer), apache2 (web/ssl endpoint).
You can expand the capacity of the service node as follows:

    $ juju add-unit landscape

This charm uses a self-contained apache and ha-proxy in the core charm
so configuration is taken care of automatically for load-balancing.

Customized Deployment
---------------------

TODO: describe multi-service deployment here
