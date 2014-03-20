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

    $ cat >lds.yaml <<EOF
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

    $ juju deploy --config=lds.yaml landscape
    $ juju deploy --config=lds.yaml postgresql
    $ juju deploy --config=lds.yaml apache2
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


Juju-Deployer
-------------

You can use juju-deployer to greatly simplify the deployment of Landscape to a
real cloud.  Inside the charm, there is a "config" directory that contains a
deployer configuration file that encapsulates all the charms and their
configuration options.

juju-deployer is packaged and available in the juju PPA. If you don't have
that PPA, you can add it like this:

    $ sudo add-apt-repository ppa:juju/stable
    $ sudo apt-get update

Then install deployer:

    $ sudo apt-get install juju-deployer

Grab the landscape charm:

    $ bzr branch lp:landscape-charm
    $ cd landscape-charm/config

Next, you will need to add in a repository and license file to use:

    $ vim license-file               # Put the license text in this file
    $ vim repo-file                  # Insert the URL part of an APT sources list line here

Then, one command to deploy.  (-v, -d, -W are optional, but nice):

    $ juju-deployer -vdW -c landscape-deployments.yaml landscape

Use the list option to view the other available targets:

    $ juju-deployer -c landscape-deployments.yaml -l

The available targets are:

  * landscape: standard deployment target. You get landscape, landscape-msg
    (the message server) and the remaining services on individual machines.
    You should use this one if you want a simple and normal deployment.
  * landscape-max: each landscape service gets its own machine.
  * landscape-dense-maas: deploys everything to the bootstrap node using lxc.
    Only works with the MAAS provider for now, due to a limitation in juju.
  * landscape-max-dense-maas: same as above, but uses the landscape-max layout.


Unit Testing
------------

The Landscape charm is fairly well unit tested and new code changes
should be submitted with unit tests.  You can run them like this:

    $ sudo apt-get install python-twisted-core
    $ make test

Integration Testing
-------------------

This charm makes use of juju-deployer and the charm-tools package to enable
end-to-end integration testing.  This is how you proceed with running
them:

    # Make sure your JUJU_ENV is *not* bootstraped, and:
    $ JUJU_ENV=<env> make integration-test
