import os

from fixtures import TestWithFixtures, TempDir

from lib.callbacks.scripts import SchemaBootstrap


class SchemaBootstrapTest(TestWithFixtures):

    def setUp(self):
        super(SchemaBootstrapTest, self).setUp()
        self.tempdir = self.useFixture(TempDir())
        self.callback = SchemaBootstrap(scripts_dir=self.tempdir.path)

    def test_standalone_config(self):
        """
        The schema script is invoked with the LANDSCAPE_CONFIG environment
        variable set to 'standalone'.
        """
        schema = self.tempdir.join("schema")
        output = self.tempdir.join("output")
        with open(schema, "w") as fd:
            fd.write("#!/bin/sh\n"
                     "echo -n $LANDSCAPE_CONFIG > %s\n" % output)
        os.chmod(schema, 0755)
        self.callback(None, None, None)
        with open(output, "r") as fd:
            self.assertEqual("standalone", fd.read())

    def test_options(self):
        """
        The schema script is invoked with the --bootstrap option.
        """
        schema = self.tempdir.join("schema")
        output = self.tempdir.join("output")
        with open(schema, "w") as fd:
            fd.write("#!/bin/sh\n"
                     "echo -n $1 > %s\n" % output)
        os.chmod(schema, 0755)
        self.callback(None, None, None)
        with open(output, "r") as fd:
            self.assertEqual("--bootstrap", fd.read())
