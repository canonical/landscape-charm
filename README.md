Overview
========

The Landscape systems management tool helps you monitor, manage and update your
entire Ubuntu infrastructure from a single interface. Part of Canonical's
Ubuntu Advantage support service, Landscape brings you intuitive systems
management tools combined with world-class support.

This charm will deploy Landscape Dedicated Server (LDS), and needs to be
connected to other charms to be fully functional. Example deployments are given
below.

For more information about Landscape, go to http://www.ubuntu.com/management

Standard Usage
==============

The typical deployment of Landscape happens using a Juju bundle. This charm is
not useful without a deployed bundle of services.

Please use one of the following bundle types depending on your needs:

  https://jujucharms.com/u/landscape/landscape-scalable/
  https://jujucharms.com/u/landscape/landscape-dense-maas/
  https://jujucharms.com/u/landscape/landscape-dense/

For the landscape-scalable case:

  sudo apt-add-repository ppa:juju/stable
  sudo apt-get update
  juju quickstart u/landscape/landscape-scalable


Customized Deployments
======================

The standard deployment of Landscape will give you the latest released code.
If you want a different version, different options, etc, you will need to
download one of the bundles, and add/change options in the file before
supplying it to juju quickstart.

On the bundle page, download the `bundle.yaml` file.


Configuration
=============

Landscape is a commercial product and as such it needs configuration of a 
license and password protected repository before deployment.  Please login to 
your "hosted account" (on landscape.canonical.com) to gather these details 
after purchasing seats for LDS.  All information is found by following a link 
on the left side of the page called "access the Landscape Dedicated Server 
archive"

license-file
------------

You can set this as a juju configuration option after deployment
on each deployed landscape-service like:

    $ juju set <landscape-service> "license-file=$(cat license-file)"


SSL
===

The pre-packaged bundles will ask the HAProxy charm to generate a self
signed certificate. While useful for testing, this must not be used for
production deployments.

For production deployments, you should include a "real" SSL certificate key
pair that has been signed by a CA that your clients trust in the haproxy service
configuration (or in the landscape-server service configuration if you need to
use your haproxy service for other services too with different certificates).


Unit Testing
============

The Landscape charm is fairly well unit tested and new code changes
should be submitted with unit tests.  You can run them like this:

    $ make test


Integration Testing
===================

This charm makes use of juju-deployer and the charm-tools package to enable
end-to-end integration testing.  This is how you proceed with running
them:

    $ juju bootstrap localhost
    $ make integration-test

Or if you want to use the LDS packages from the lds-trunk PPA:

    $ JUJU_MODEL=<model> make integration-test-trunk

The JUJU_MDOEL environment variable can be omitted if you want to use the
current model.
