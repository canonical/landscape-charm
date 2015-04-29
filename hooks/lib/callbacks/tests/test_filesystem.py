import base64

from charmhelpers.core.services.base import ServiceManager

from lib.tests.helpers import HookenvTest
from lib.tests.offline_fixture import RootDir
from lib.callbacks.filesystem import EnsureConfigDir, WriteCustomSSLCertificate


class EnsureConfigDirTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(EnsureConfigDirTest, self).setUp()
        self.root_dir = self.useFixture(RootDir())
        self.callback = EnsureConfigDir(self.root_dir.paths)

    def test_options(self):
        """
        The callback creates a config dir symlink if needed.
        """
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [{"hosted": [{"deployment-mode": "edge"}]}],
        }])
        self.callback(manager, "landscape", None)
        self.assertIsNotNone(self.root_dir.paths.config_link("edge"))


class WriteCustomSSLCertificateTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(WriteCustomSSLCertificateTest, self).setUp()
        self.root_dir = self.useFixture(RootDir())
        self.callback = WriteCustomSSLCertificate(self.root_dir.paths)

    def test_haproxy_certificate(self):
        """
        If the config doesn't specify any SSL certificate, the haproxy one
        is used.
        """
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [
                {"website": [{"ssl_cert": base64.b64encode("<haproxy ssl>")}]},
                {"config": {}},
            ],
        }])
        self.callback(manager, "landscape", None)
        with open(self.root_dir.paths.ssl_certificate(), "r") as fd:
            self.assertEqual("<haproxy ssl>", fd.read())

    def test_config_certificate(self):
        """
        If the config specifies an SSL certificate, then the callback picks
        that one.
        """
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [
                {"website": [{"ssl_cert": base64.b64encode("<haproxy ssl>")}]},
                {"config": {"ssl-cert": base64.b64encode("<config ssl>")}},
            ],
        }])
        self.callback(manager, "landscape", None)
        with open(self.root_dir.paths.ssl_certificate(), "r") as fd:
            self.assertEqual("<config ssl>", fd.read())
