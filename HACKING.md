Unit Testing
============

Code changes should be accompanied by unit test cases.  To run the test cases:

    make test


Integration Testing
===================

This charm comes with an integration test suite.  You can run it as follows:

    make integration-test

N.B., It will deploy into a real juju environment. It uses the juju-test
command to facilitate this, which takes care of bootstrapping for you.  It
will use whatever 'juju env' reports as your current environment.  It will use
a number of machines to do this test -- it should work on a local environment
(LXC), but could be quite resource intensive.

Please also note that if you want to deploy the current charm branch you are
working on, you need to change the branch URL in the landscape-deployments.yaml
file to point to your branch and commit all changes.  After you are done with
testing, remember to return the branch URL to what it was before


Testing with Dependent Upstream Charms
======================================

To test with the latest revisions of all dependent charms, you can use a 
convenient makefile target:

    make update-charm-revision-numbers

After running this, you can use bzr diff to see what (if any) changes were
made to landscape-deployments.yaml.
