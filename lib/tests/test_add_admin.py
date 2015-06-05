from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.add_admin import AddAdminUserAction
from lib.paths import SCHEMA_SCRIPT


class AddAdminUserActionTest(HookenvTest):

    def setUp(self):
        super(AddAdminUserActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(SCHEMA_SCRIPT)
        self.subprocess.add_fake_executable("service")
        self.action = AddAdminUserAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The AddAdminUserAction stops the Landscape services.
        """
        self.action()
        # HookenvStub.action_get returns 'key-value' as
        # the value for each 'key'.
        self.assertEqual(
            [(("/usr/bin/landscape-schema", "--create-lds-account-only",
               "--admin-name", "name-value", "--admin-email", "email-value",
               "--admin-password", "password-value"), {})],
            self.subprocess.calls)
