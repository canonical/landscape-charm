Unit Testing
============

Code changes should be accompanied by unit test cases.  To run the test cases:

    make test


Integration Testing
===================

This charm comes with an integration test suite, which lives in the 'tests'
directory.  You can run it as follows:

    make integration-test

N.B., It will deploy into a real juju environment. It uses the juju-test
command to facilitate this, which takes care of bootstrapping for you.  It
will use whatever 'juju env' reports as your current environment.  It will use
a number of machines to do this test -- it should work on a local environment
(LXC), but could be quite resource intensive.


Running parts of the integration tests
--------------------------------------

Running all the integration tests may take quite a while, and sometimes
you want to just run the ones that you are working on. To do that, you
can bootstrap the Juju environment yourself, and then use the zope
testrunner directly. For example:

    zope-testrunner3 -vv --path tests --tests-pattern basic --test some_test

If the different services already are deployed, the command above is enough.
But if you run it against an empty environment, you have to remember to pass
along environment variables that affect the deployment, such as
LS_CHARM_SOURCE=lds-trunk-ppa.


Running integration tests on dense MAAS deployment
--------------------------------------------------

It's possible to run the integration tests on a dense MAAS deployment,
where all the services run on the bootstrap node. But given that it's a
bit different from other deployments, you have to explicitly tell that
it's such a deployment using the DENSE_MAAS environment variable. For
example:

    DENSE_MAAS=1 make integration-test-trunk

Or, if you already have the environment bootstrapped:

    DENSE_MAAS=1 LS_CHARM_SOURCE=lds-trunk-ppa zope-testrunner3 -vv \
        --path tests --tests-pattern basic --test some_test


Testing with Dependent Upstream Charms
======================================

To test with the latest revisions of all dependent charms, you can use a 
convenient makefile target:

    make update-charm-revision-numbers

After running this, you can use 'bzr diff bundles' to see what (if any)
changes were made to landscape-deployments.yaml.
