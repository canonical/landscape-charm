from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.bootstrap import BootstrapAction
from lib.paths import SCHEMA_SCRIPT


class BootstrapActionTest(HookenvTest):

    def setUp(self):
        super(BootstrapActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.subprocess.add_fake_executable("service")
        self.action = BootstrapAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The BootstrapAction calls the landscape-schema script to create an
        administrator account.
        """
        self.action()
        # HookenvStub.action_get returns 'key-value' as
        # the value for each 'key'.
        [(command, kwargs)] = self.subprocess.calls
        self.assertEqual(
            (("/usr/bin/landscape-schema", "--create-lds-account-only",
              "--admin-name", "admin-name-value",
              "--admin-email", "admin-email-value",
              "--admin-password", "admin-password-value"), {}),
            (command, kwargs))

