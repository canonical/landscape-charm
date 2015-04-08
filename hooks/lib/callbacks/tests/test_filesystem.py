import os

from fixtures import TempDir

from charmhelpers.core.services.base import ServiceManager

from lib.tests.helpers import HookenvTest
from lib.callbacks.filesystem import EnsureConfigDir


class EnsureConfigDirTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(EnsureConfigDirTest, self).setUp()
        self.configs_dir = self.useFixture(TempDir())
        self.callback = EnsureConfigDir(self.configs_dir.path)

    def test_options(self):
        """
        The callback creates a config dir symlink if needed.
        """
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [{"hosted": [{"deployment-mode": "edge"}]}],
        }])
        self.callback(manager, "landscape", None)
        self.assertIsNotNone(os.lstat(self.configs_dir.join("edge")))
