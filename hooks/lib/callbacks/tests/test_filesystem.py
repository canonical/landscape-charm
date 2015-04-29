import base64
import tempfile
import urllib2

from charmhelpers.core.services.base import ServiceManager

from lib.hook import HookError

from lib.tests.stubs import HostStub
from lib.tests.helpers import HookenvTest

from lib.tests.rootdir import RootDir
from lib.callbacks.filesystem import (
    EnsureConfigDir, WriteCustomSSLCertificate, WriteLicenseFile)


class EnsureConfigDirTest(HookenvTest):

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


class WriteLicenseFileTest(HookenvTest):

    def setUp(self):
        super(WriteLicenseFileTest, self).setUp()
        self.host = HostStub()
        self.callback = WriteLicenseFile(host=self.host)

    def test_license_file_unset(self):
        """
        If license-file is unset in the the config, no license file is created.
        """
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [],
        }])
        self.callback(manager, "landscape", None)

        self.assertEqual([], self.host.calls)

    def test_license_file_data(self):
        """
        If the config specifies a license file data directly as
        the base64-encoded value, it is decoded and written
        into a license file on the unit.
        """
        license_data = 'Test license data'
        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [
                {"config": {
                    "license-file": base64.b64encode(license_data)
                }},
            ],
        }])
        self.callback(manager, "landscape", None)

        self.assertEqual([
            ("write_file", ('/etc/landscape/license.txt', 'Test license data'),
             {'owner': 'landscape', 'group': 'root', 'perms': 0o640})
        ], self.host.calls)

    def test_license_file_bad_data(self):
        """
        When license-file is not a URL and not base64-encoded data, fails
        with HookError.
        """
        self.addCleanup(setattr, urllib2, "urlopen", urllib2.urlopen)

        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [
                {"config": {
                    "license-file": "bad data",
                }},
            ],
        }])
        self.assertRaises(HookError, self.callback, manager, "landscape", None)

    def test_license_file_file_url(self):
        """
        If the config specifies a license file using a local file:// URL,
        contents of that file are transferred verbatim to the license file
        on the unit.
        """
        with tempfile.NamedTemporaryFile() as source_license_file:
            source_license_file.write('Test license data')
            source_license_file.flush()
            source_license_url = 'file://' + source_license_file.name

            manager = ServiceManager([{
                "service": "landscape",
                "required_data": [
                    {"config": {
                        "license-file": source_license_url,
                    }},
                ],
            }])
            self.callback(manager, "landscape", None)

            self.assertEqual([
                ("write_file",
                 ('/etc/landscape/license.txt', 'Test license data'),
                 {'owner': 'landscape', 'group': 'root', 'perms': 0o640})
            ], self.host.calls)

    def test_license_file_http_url(self):
        """
        If the config specifies a license file using a local file:// URL,
        contents of that file are transferred verbatim to the license file
        on the unit.
        """
        class FakeUrl(object):
            def read(self):
                return 'Test license data'
        self.addCleanup(setattr, urllib2, "urlopen", urllib2.urlopen)
        urllib2.urlopen = lambda url: FakeUrl()

        source_license_url = 'http://blah'

        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [
                {"config": {
                    "license-file": source_license_url,
                }},
            ],
        }])
        self.callback(manager, "landscape", None)

        self.assertEqual([
            ("write_file", ('/etc/landscape/license.txt', 'Test license data'),
             {'owner': 'landscape', 'group': 'root', 'perms': 0o640})
        ], self.host.calls)

    def test_license_file_bad_url(self):
        """
        If the config specifies a license file using a local file:// URL,
        contents of that file are transferred verbatim to the license file
        on the unit.
        """
        self.addCleanup(setattr, urllib2, "urlopen", urllib2.urlopen)

        def stub_urlopen(url):
            raise urllib2.URLError("error")
        urllib2.urlopen = stub_urlopen

        source_license_url = 'http://blah'

        manager = ServiceManager([{
            "service": "landscape",
            "required_data": [
                {"config": {
                    "license-file": source_license_url,
                }},
            ],
        }])
        self.assertRaises(HookError, self.callback, manager, "landscape", None)
