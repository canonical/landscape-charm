Overview
========

The Landscape systems management tool helps you monitor, manage and update your
entire Ubuntu infrastructure from a single interface. Part of Canonical’s
Ubuntu Advantage support service, Landscape brings you intuitive systems
management tools combined with world-class support.

This charm will deploy the dedicated version of Landscape (LDS), and needs to be
connected to other charms to be fully functional.  Example deployments are given
below.

For more information about Landscape, go to http://www.ubuntu.com/management


Usage
=====

The typical deployment of Landscape happens using juju-deployer.  This charm is
not useful without a deployed bundle of services.  Please read below for how to
deploy all services necessary for a functioning install of LDS.

Juju-Deployer
-------------

NOTE: This section will be superseded by a juju "bundle", when that is ready.

You can use juju-deployer to greatly simplify the deployment of Landscape to a
real cloud.  Inside the charm, there is a "config" directory that contains a
deployer configuration file that encapsulates all the charms and their
configuration options into what we call "deployer targets".

juju-deployer is packaged and available in the juju PPA. If you don't have that
PPA, you can add it like this:

    $ sudo add-apt-repository ppa:juju/stable
    $ sudo apt-get update

Then install deployer:

    $ sudo apt-get install juju-deployer

Grab the landscape charm:

    $ bzr branch lp:~landscape-charmers/charms/precise/landscape-server/trunk
    $ cd trunk/config

Prepare the repository and license files (See "Configuration" section for more
details):

    $ vim license-file   # Put the license text in this file
    $ vim repo-file      # Put the URL part of an APT sources.list line here

Change the passwords used in the landscape-deployments.yaml file in the
"monitoring_password" and "landscape-password" keys to new values:

    $ vim landscape-deployments.yaml

Now we are ready to deploy (the -w 180, -v, -d, -W flags are optional, but
nice).  The "landscape" deployer target is the one you should start with. It
uses 6 machines plus the juju bootstrap node:

    $ juju-deployer -vdW -w 180 -c landscape-deployments.yaml landscape

NOTE: After juju-deployer finishes, the deployment is not entirely ready yet.

Hooks are still running, and it can be a few minutes until everything is ready.
You can point your browser to the apache2/0 unit and keep reloading until you
see the form to create the first Landscape administrator, and/or follow the
output of juju debug-log until it shows that all hooks are done.

To view what other deployment targets are available, use the list option:

    $ juju-deployer -c landscape-deployments.yaml -l


Configuration
=============

Landscape is a commercial product, as such it needs configuration of a license
and password protected repository before deployment.  Please login to your
"hosted account" (on landscape.canonical.com) to gather these details after
purchasing seats for LDS.  All information is found by following a link on the
left side of the page called "access the Landscape Dedicated Server archive"

license-file
------------

`config/landscape-deployments.yaml` supports reading a `license-file` in the
`config` directory.  Take the license file you downloaded, put it in the file
called `config/license-file`, and juju-deployer should read it in and deploy as
usual.

You can also set this as a juju configuration option after deployment
on each deployed landscape-service like:

    $ juju set <landscape-service> "license-file=$(cat license-file)"


repository
----------

Put just the URL part of the "deb ..." line into a file called
`config/repo-file` and juju-deployer should read it in and depoy as usual.

At this time, this setting is not changeable after Landscape has been
deployed.

Example:
    
    $ cat config/repo-file
    https://username:password@archive.landscape.canonical.com/
    $

SSL
===

The included deployment targets will ask Apache to generate a self signed
certificate. While useful for testing, this must not be used for production
deployments.

For production deployments, you should include the "real" SSL certificate key
pair in the apache charm configuration.


Deployment targets
==================

The config/landscape-deployments.yaml deployer configuration file has two
deployment targets available:

  * landscape
  * landscape-dense-maas

Targets that start with an underscore should be ignored as they are used
internally only. Your choice of target should be made taking into consideration
the scaling options available for each one and existing resources in your
environment.

"landscape" target
------------------
The "landscape" target is a good compromise between scalability and resource
usage. This deployment will give you 6 units (plus the bootstrap node):
  * single database server, acting as master
  * one landscape message server unit, responsible for managing the computers
    you have registered with landscape
  * one other landscape unit which hosts the other less resource-intensive
    landscape services
  * apache, haproxy and rabbitmq-server each in its own unit

There are three common scaling out options for this deployment:
 * if you need Landscape to handle more computers, add another landscape-msg
   unit
 * if you need to allow more concurrent access for administrators, add another
   landscape unit
 * add another database unit if you want database replication. The replication
   configuration happens automatically.

Landscape dense target
----------------------
If you are using juju backed by the MAAS provider, and have big enough machines
registered with MAAS, you can try out the landscape-dense-maas target.  It
behaves like its "landscape" counterpart, but everything is deployed into the
bootstrap node using LXC.

The reason it only works with MAAS for now is that MAAS is the only provider so
far that can offer external network connectivity to units deployed into LXC.

Customized deployments
-----------------------
You can customize the Landscape deployment quite a lot. Via the "services"
charm config option you can select exactly which landscape services (or
processes) you want running where, and also how many copies per unit. Look at
the config.yaml file for details on how to use this option.


Unit Testing
============

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
    $ sudo apt-get install python-pyscopg2 python-mocker python-psutil
    $ JUJU_ENV=<env> make integration-test
