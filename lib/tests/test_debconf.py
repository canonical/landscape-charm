import subprocess

from unittest import TestCase

from lib.debconf import DebConf
from lib.paths import DPKG_RECONFIGURE, DEBCONF_SET_SELECTIONS
from lib.tests.stubs import SubprocessStub

PACKAGE = "some-package"
SCHEMA = {
    "cool-option": "string",
    "do-you-like-me": "boolean"
}


class DebConfTest(TestCase):

    def setUp(self):
        super(DebConfTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.debconf = DebConf(PACKAGE, SCHEMA, subprocess=self.subprocess)

    def test_set(self):
        """
        The set() method invokes debconf-set-selections, feeding it with
        a formatted input line for each option.
        """
        self.subprocess.add_fake_executable(DEBCONF_SET_SELECTIONS)
        self.debconf.set({
            "cool-option": "nice",
            "do-you-like-me": "yes"})
        [process] = self.subprocess.processes
        self.assertEqual({"stdin": subprocess.PIPE}, process.kwargs)
        self.assertEqual(
            "some-package some-package/cool-option string nice\n"
            "some-package some-package/do-you-like-me boolean yes\n",
            process.input)

    def test_set_unknown_option(self):
        """
        The set() method raises an error when trying to set an option which
        was not declared in the schema.
        """
        self.assertRaises(RuntimeError, self.debconf.set, {"unknonw": "foo"})

    def test_reconfigure(self):
        """
        The reconfigure() method invokes dpkg-reconfigure with the
        noninteractive frontend.
        """
        self.subprocess.add_fake_executable(DPKG_RECONFIGURE)
        self.debconf.reconfigure()
        [call] = self.subprocess.calls
        self.assertEqual(
            ([DPKG_RECONFIGURE, "-fnoninteractive", "some-package"], {}),
            call)
