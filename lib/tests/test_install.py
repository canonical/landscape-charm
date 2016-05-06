import os

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import FetchStub, SubprocessStub
from lib.install import InstallHook


class InstallHookTest(HookenvTest):

    def setUp(self):
        super(InstallHookTest, self).setUp()
        self.fetch = FetchStub()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable("apt-mark")
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
        flag = os.path.join(charm_dir, "foo-run")
        hook = os.path.join(charm_dir, "exec.d", "foo", "charm-pre-install")
        os.makedirs(os.path.dirname(hook))
        with open(hook, "w") as fd:
            fd.write("#!/bin/sh\ntouch %s\n" % flag)
        os.chmod(hook, 0755)
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.hook()
        self.assertTrue(os.path.exists(flag))

    def test_pre_install_hook_fail(self):
        """
        If a pre-install hook fails, the hook returns 1 and logs the error.
        """
        charm_dir = self.hookenv.charm_dir()
        hook = os.path.join(charm_dir, "exec.d", "foo", "charm-pre-install")
        os.makedirs(os.path.dirname(hook))
        with open(hook, "w") as fd:
            fd.write("#!/bin/sh\ntexit 127\n")
        os.chmod(hook, 0755)
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.assertEqual(1, self.hook())
        self.assertEqual(
            "Command '%s' returned non-zero exit status 127" % hook,
            self.hookenv.messages[-1][0])

    def test_pre_install_hooks_ignores(self):
        """
        Files that are not executable or don't match the expected name pattern
        are just ignored.
        """
        charm_dir = self.hookenv.charm_dir()
        flag = os.path.join(charm_dir, "foo-run")
        hook1 = os.path.join(charm_dir, "exec.d", "foo", "charm-pre-install")
        hook2 = os.path.join(charm_dir, "exec.d", "foo", "no-match")
        os.makedirs(os.path.dirname(hook1))
        with open(hook1, "w") as fd:
            fd.write("#!/bin/sh\ntouch %s\n" % flag)
        with open(hook2, "w") as fd:
            fd.write("#!/bin/sh\ntouch %s\n" % flag)
        os.chmod(hook2, 0755)
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.hook()
        self.assertFalse(os.path.exists(flag))

    def test_install_holds_packages(self):
        """
        The install hook holds the landscape packages.
        """
        self.hookenv.config()["source"] = "ppa:landscape/14.10"
        self.hook()
        expected_call = [
            "apt-mark", "hold", "landscape-server", "landscape-hashids"]
        self.assertEqual(expected_call, self.subprocess.calls[0][0])
