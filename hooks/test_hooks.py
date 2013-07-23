import hooks
import unittest
import yaml
import tempfile
import os
import pycurl

class TestJuju(object):
    _relation_data = {}
    def __init__(self):
        self.license_file = "LICENSE_FILE_TEXT"

    def relation_set(self, *args, **kwargs):
        self._relation_data = dict(self._relation_data, **kwargs)
        for i in args:
            (k, v) = i.split("=")
            self._relation_data[k] = v
        pass

    def unit_get(self, *args):
        return "localhost"

    def juju_log(self, *args, **kwargs):
        pass

    def config_get(self, scope=None):
        if scope is None:
            return {"services": "foo bar baz buz"}
        elif scope == "license-file":
            return self.license_file
        pass

    def relation_get(self, scope=None, unit_name=None, relation_id=None):
        pass


class TestHooks(unittest.TestCase):
    all_services = [
            {"service_name": "foo",
             "servers": [[
                 "foo", "localhost", "80",
                 "check inter 2000 rise 2 fall 5 maxconn 50"]],
             "service_options": [
                 "mode http", "balance leastconn", "option httpchk foo"]},
            {"service_name": "bar",
             "servers": [[
                 "bar", "localhost", "81",
                 "check inter 2000 rise 2 fall 5 maxconn 50"]],
             "service_options": [
                 "mode http", "balance leastconn",
                 "option httpchk GET / HTTP/1.0"]},
            {"service_name": "baz",
             "servers": [["baz", "localhost", "82", "server"]],
             "service_options": ["options"]}]

 
    def setUp(self):
        hooks.SERVICE_PROXY = {"foo": {"port": "80", "httpchk": "foo"},
                         "bar": {"port": "81"},
                         "baz": {"port": "82", "httpchk": None,
                                 "server_options": "server",
                                 "service_options": ["options"]}}
        hooks.juju = TestJuju()

    def assertFileContains(self, filename, text):
        with open(filename, 'r') as fp:
            contents = fp.read()
        self.assertTrue(text in contents)

    def assertFilesEqual(self, file1, file2):
        with open(file1, 'r') as fp1:
            contents1 = fp1.read()
        with open(file2, 'r') as fp2:
            contents2 = fp2.read()
        self.assertEqual(contents1, contents2)

    def test_format_service(self):
        result = hooks._format_service("bar", **hooks.SERVICE_PROXY["bar"])
        baseline = {"service_name": "bar",
                    "servers": [[
                        "bar", "localhost", "81",
                        "check inter 2000 rise 2 fall 5 maxconn 50"]],
                    "service_options": [
                        "mode http", "balance leastconn",
                        "option httpchk GET / HTTP/1.0"]}
        self.assertEqual(baseline, result)

    def test_format_service_with_options(self):
        result = hooks._format_service("foo", **hooks.SERVICE_PROXY["foo"])
        baseline = {"service_name": "foo",
                    "servers": [[
                        "foo", "localhost", "80",
                        "check inter 2000 rise 2 fall 5 maxconn 50"]],
                    "service_options": [
                        "mode http", "balance leastconn", "option httpchk foo"]}
        self.assertEqual(baseline, result)

    def test_format_service_with_more_options(self):
        result = hooks._format_service("baz", **hooks.SERVICE_PROXY["baz"])
        baseline = {"service_name": "baz",
                    "servers": [["baz", "localhost", "82", "server"]],
                    "service_options": ["options"]}
        self.assertEqual(baseline, result)

    def test_get_services(self):
        result = hooks._get_services()
        baseline = self.all_services
        self.assertEqual(baseline, result)

    def test_website_relation_joined(self):
        hooks.website_relation_joined()
        baseline = {
            "services": yaml.safe_dump(self.all_services),
            "hostname": "localhost",
            "port": 80}
        self.assertEqual(baseline, hooks.juju._relation_data)

    def test_amqp_relation_joined(self):
        hooks.amqp_relation_joined()
        baseline = {
            "username": "landscape",
            "vhost": "landscape"}
        self.assertEqual(baseline, hooks.juju._relation_data)

    def test__download_file_success(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        with tmp as fp:
            fp.write("foobar")
            fp.flush()
        output = hooks._download_file("file://%s" % tmp.name)
        os.unlink(tmp.name)
        self.assertTrue("foobar" in output)

    def test__download_file_failure(self):
        self.assertRaises(pycurl.error, hooks._download_file, "file://FOO/NO/EXIST")

    def test__replace_in_file(self):
        tmp = tempfile.NamedTemporaryFile(delete=False)
        with tmp as fp:
            fp.write("foo\nbar\nbaz\n")
            fp.flush()

        hooks._replace_in_file(tmp.name, r'^f..$', "REPLACED")

        with open(tmp.name, 'r') as fp:
            content = fp.read()
        os.unlink(tmp.name)
        self.assertEquals("REPLACED\nbar\nbaz\n", content)

    def test__enable_service(self):
        """ Create a simple service enablement of a file with comments """
        default = tempfile.NamedTemporaryFile(delete=False)
        target = tempfile.NamedTemporaryFile(delete=False)
        with default as fp:
            fp.write('# Comment test\nRUN_APPSERVER="no"')
            fp.flush()
        with target as fp:
            fp.write('# Comment test\nRUN_APPSERVER=yes')
            fp.flush()
        hooks.LANDSCAPE_DEFAULT_FILE = default.name
        hooks._enable_services(["appserver"])
        self.assertFilesEqual(default.name, target.name)
        os.unlink(default.name)
        os.unlink(target.name)
        pass

    def test__enable_wrong_service(self):
        """ Create a simple service enablement of a file with comments """
        default = tempfile.NamedTemporaryFile(delete=False)
        with default as fp:
            fp.write('# Comment test\nRUN_APPSERVER="no"')
            fp.flush()
        hooks.LANDSCAPE_DEFAULT_FILE = default.name
        self.assertRaises(Exception, hooks._enable_services, ["foobar"])
        os.unlink(default.name)
        pass

    def test__install_license_text(self):
        """ Install a license with as a string """
        license_file = tempfile.NamedTemporaryFile(delete=False)
        hooks.LANDSCAPE_LICENSE_DEST = license_file.name
        hooks._install_license()
        self.assertFileContains(license_file.name, "LICENSE_FILE_TEXT")
        os.unlink(license_file.name)

    def test__install_license_url(self):
        """ Install a license with as a url """
        dest = tempfile.NamedTemporaryFile(delete=False)
        source = tempfile.NamedTemporaryFile(delete=False)
        with source as fp:
            fp.write("LICENSE_FILE_TEXT from curl")
            fp.flush()
        hooks.LANDSCAPE_LICENSE_DEST = dest.name
        hooks.juju.license_file = "file://%s" % source.name
        hooks._install_license()
        self.assertFileContains(dest.name, "LICENSE_FILE_TEXT from curl")
        os.unlink(source.name)
        os.unlink(dest.name)
