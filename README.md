Overview
--------

This charm is the service-component of the landscape multi-service charm.  It
will deploy the dedicated version of landsacpe (LDS), and needs to be
connected to the landscape-core charm to be fully funtional.  Example
deployments are given below.

For more information about Landscape, please visit
[Canonical's website](http://canonical.com/landscape).

Usage
-----

The typical deployment of landscape is as follows:

**Configuration**

Landscape will not run without external configuration.  The following
options represent the basic options needed to get landscape up and going.
You can find the PPA and license information in the landscape GUI.  Look on
the left side for "Dedicated".

    $ cat >lds.cfg <<EOF
        landscape-core:
            repository: https://user:pass@ppa-server/ppa-path/
            license-file: |
              <license file here>
            certificate: AUTO
        landscape-service:
            repository: https://user:pass@ppa-server/ppa-path/
            license-file: |
              <license file here>
            services: msgserver appserver pingserver combo-loader
        postgresql:
            extra-packages: python-apt postgresql-contrib postgresql-9.1-debversion
    EOF

**Deployment**

Once configured, you can deploy with the following commands:

    $ juju deploy --config=lds.cfg landscape-core
    $ juju deploy --config=lds.cfg landscape-service
    $ juju deploy --config=lds.cfg postgresql
    $ juju deploy --config=lds.cfg rabbitmq-server
    $ juju add-relation landscape-core landscape-service
    $ juju add-relation landscape-core:db-admin postgresql:db-admin
    $ juju add-relation landscape-core rabbitmq-server
    $ juju add-relation landscape-service:db-admin postgresql:db-admin
    $ juju add-relation landscape-service rabbitmq-server

This will result in a landscape cluster of 4 nodes.  Service, core, postgresql
(database), and rabbitmq (message server).  You can expand the capacity of
the service node as follows:

    $ juju add-unit landscape-service

This charm uses a self-contained apache and ha-proxy in the core charm
so configuration is taken care of automatically for load-balancing.
