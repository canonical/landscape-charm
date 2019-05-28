from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub
from lib.bootstrap import BootstrapAction
from lib.paths import API_SCRIPT

API_SCRIPT_STDOUT = """
{"LANDSCAPE_API_KEY": "key-xyz", "LANDSCAPE_API_SECRET": "secret-123"}
"""


class BootstrapActionTest(HookenvTest):

    def setUp(self):
        super(BootstrapActionTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(
            API_SCRIPT, stdout=API_SCRIPT_STDOUT)
        self.subprocess.add_fake_executable("service")
        self.action = BootstrapAction(
            hookenv=self.hookenv, subprocess=self.subprocess)

    def test_run(self):
        """
        The BootstrapAction calls the landscape-api to create an
        administrator account.
        """
        self.action()
        # HookenvStub.action_get returns 'key-value' as
        # the value for each 'key'.
        [(command, kwargs)] = self.subprocess.calls
        self.assertEqual(
            ["/usr/bin/landscape-api", "call",
             "BootstrapLDS", "--json",
             "admin_name=admin-name-value",
             "admin_email=admin-email-value",
             "admin_password=admin-password-value",
             "registration_key=registration-key-value"],
            command)
        self.assertEqual(
            {'env': {'LANDSCAPE_API_KEY': 'anonymous',
                     'LANDSCAPE_API_SECRET': 'anonymous',
                     'LANDSCAPE_API_URI': 'http://localhost:9080/api/'}},
            kwargs)
        self.assertEqual(
            [{"api-credentials": {"secret": "secret-123", "key": "key-xyz"}}],
            self.hookenv.action_sets)

    def test_run_without_registration_key(self):
        """
        The BootstrapAction calls the landscape-api to create an
        administrator account without setting the registration_key.
        """
        self.hookenv.action_set({"registration-key": ""})
        self.action()
        # HookenvStub.action_get returns 'key-value' as
        # the value for each 'key'.
        [(command, kwargs)] = self.subprocess.calls
        self.assertEqual(
            ["/usr/bin/landscape-api", "call",
             "BootstrapLDS", "--json",
             "admin_name=admin-name-value",
             "admin_email=admin-email-value",
             "admin_password=admin-password-value"],
            command)
        self.assertEqual(
            {'env': {'LANDSCAPE_API_KEY': 'anonymous',
                     'LANDSCAPE_API_SECRET': 'anonymous',
                     'LANDSCAPE_API_URI': 'http://localhost:9080/api/'}},
            kwargs)
        self.assertEqual(
            [{"api-credentials": {"secret": "secret-123", "key": "key-xyz"}}],
            self.hookenv.action_sets)
