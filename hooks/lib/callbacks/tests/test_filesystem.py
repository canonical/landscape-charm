import os
import base64

from fixtures import TempDir

from charmhelpers.core.services.base import ServiceManager

from lib.tests.helpers import HookenvTest
from lib.callbacks.filesystem import EnsureConfigDir, WriteCustomSSLCertificate


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


class WriteCustomSSLCertificateTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(WriteCustomSSLCertificateTest, self).setUp()
        self.certs_dir = self.useFixture(TempDir())
        self.callback = WriteCustomSSLCertificate(self.certs_dir.path)

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
        with open(self.certs_dir.join("landscape_server_ca.crt"), "r") as fd:
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
        with open(self.certs_dir.join("landscape_server_ca.crt"), "r") as fd:
            self.assertEqual("<config ssl>", fd.read())
