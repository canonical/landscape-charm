import os

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.install import InstallHook


class InstallHookTest(HookenvTest):

    def setUp(self):
        super(InstallHookTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.hook = InstallHook(
            hookenv=self.hookenv, fetch=self.fetch, subprocess=self.subprocess)

    def test_run(self):
        """
        The L{InstallHook} configures APT sources and install the needed
        packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.assertEqual(0, self.hook())
        self.assertNotEqual([], self.fetch.sources)
        self.assertNotEqual([], self.fetch.installed)

    def test_pre_install_hooks(self):
        """
        The InstallHook invokes any pre-install hook found in the exec.d/
        sub-directory.
        """
        charm_dir = self.hookenv.charm_dir()
        hook = os.path.join(charm_dir, "exec.d", "foo", "charm-pre-install")
        os.makedirs(os.path.dirname(hook))
        with open(hook, "w") as fd:
            fd.write("#!/bin/sh\nexit\n")
        os.chmod(hook, 0755)
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.hook()
        self.assertEqual(
            [(("/bin/sh", "-c", hook), {})], self.subprocess.calls)
