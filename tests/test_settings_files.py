# Copyright 2022 Canonical Ltd

import os
from base64 import b64encode
from io import BytesIO, StringIO
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.error import URLError

from settings_files import (
    CONFIGS_DIR, LICENSE_FILE, LicenseFileReadException, SSLCertReadException,
    configure_for_deployment_mode, merge_service_conf, prepend_default_settings,
    update_default_settings, update_service_conf, write_license_file, write_ssl_cert)


class CapturingBytesIO(BytesIO):
    """
    A BytesIO subclass that maintains its contents after being closed.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.captured = b""

    def close(self, *args, **kwargs):
        self.captured = self.getvalue()

        return super().close(*args, **kwargs)


class CapturingStringIO(StringIO):
    """
    A StringIO subclass that maintains its contents after being closed.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.captured = ""

    def close(self, *args, **kwargs):
        self.captured = self.getvalue()

        return super().close(*args, **kwargs)


class ConfigureForDeploymentModeTestCase(TestCase):

    @patch("os.symlink")
    def test_configure_for_deployment_mode_standalone(self, symlink_mock):
        """
        The default mode, "standalone", should result in no changes.
        """
        configure_for_deployment_mode("standalone")

        symlink_mock.assert_not_called()

    @patch("os.symlink")
    def test_configure_for_deployment_mode_other(self, symlink_mock):
        """
        Modes other than the magic "standalone" should symlink to a similarly named directory.
        """
        configure_for_deployment_mode("elite_dangerous")

        symlink_mock.assert_called_once_with(
            os.path.join(CONFIGS_DIR, "standalone"),
            os.path.join(CONFIGS_DIR, "elite_dangerous")
        )

    @patch("os.path.exists")
    @patch("os.symlink")
    def test_configure_for_deployment_mode_exists(self, symlink_mock, path_exists_mock):
        """
        If the symlink already exists, nothing is done.
        """
        path_exists_mock.return_value = True

        configure_for_deployment_mode("jabberwocky")

        path_exists_mock.assert_called_once_with(os.path.join(CONFIGS_DIR, "jabberwocky"))
        symlink_mock.assert_not_called()


class MergeServiceConfTestCase(TestCase):

    def test_merge_service_conf_new(self):
        """
        Tests that a new section and key are created in the existing
        config file.
        """
        old_conf = "[global]\nfoo = bar\nbat = baz\n"
        infile = StringIO(old_conf)
        outfile = CapturingStringIO()
        new_conf = "[new]\ncat = meow\n"

        i = 0

        def return_conf(path, *args, **kwargs):
            nonlocal i
            retval = (infile, outfile)[i]
            i += 1
            return retval

        with patch("builtins.open") as open_mock:
            open_mock.side_effect = return_conf
            merge_service_conf(new_conf)

        self.assertIn(old_conf, outfile.captured)
        self.assertIn(new_conf, outfile.captured)

    def test_merge_service_conf_override(self):
        """
        Tests that a provided config overrides values in the old config.
        """
        old_conf = "[global]\nleft = true\ntouched = false\n"
        infile = StringIO(old_conf)
        outfile = CapturingStringIO()
        new_conf = "[global]\ntouched = true\n"

        i = 0

        def return_conf(path, *args, **kwargs):
            nonlocal i
            retval = (infile, outfile)[i]
            i += 1
            return retval

        with patch("builtins.open") as open_mock:
            open_mock.side_effect = return_conf
            merge_service_conf(new_conf)

        self.assertIn("left = true", outfile.captured)
        self.assertIn("touched = true", outfile.captured)
        self.assertNotIn("touched = false", outfile.captured)


class PrependDefaultSettingsTestCase(TestCase):

    def test_prepend(self):
        infile = StringIO("# Second line")
        outfile = CapturingStringIO()

        def return_settings(path, mode):
            if mode == "r":
                return infile
            else:
                return outfile

        with patch("builtins.open") as mock_open:
            mock_open.side_effect = return_settings
            prepend_default_settings({"TEST": "yes"})

        self.assertEqual(outfile.captured, 'TEST="yes"\n# Second line')


class UpdateDefaultSettingsTestCase(TestCase):

    def test_setting_exists(self):
        """Tests that a setting gets updated if it exists."""
        infile = StringIO('TEST="no"\n')
        outfile = CapturingStringIO()

        def return_settings(path, mode):
            if mode == "r":
                return infile
            else:
                return outfile

        with patch("builtins.open") as mock_open:
            mock_open.side_effect = return_settings
            update_default_settings({"TEST": "yes"})

        self.assertEqual(outfile.captured, 'TEST="yes"\n')

    def test_setting_does_not_exist(self):
        """
        Tests that nothing is changed if the setting does not exist.
        """
        infile = StringIO('TEST="no"\n#comment\n')
        outfile = CapturingStringIO()

        def return_settings(path, mode):
            if mode == "r":
                return infile
            else:
                return outfile

        with patch("builtins.open") as mock_open:
            mock_open.side_effect = return_settings
            update_default_settings({"TEST2": "yes"})

        self.assertEqual(outfile.captured, 'TEST="no"\n#comment\n')


class UpdateServiceConfTestCase(TestCase):

    def test_no_section(self):
        """
        Tests that a new config section is created if it does not
        exist.
        """
        infile = StringIO("[fixed]\nold = no\n")
        outfile = CapturingStringIO()

        i = 0

        def return_conf(path, *args, **kwargs):
            nonlocal i
            retval = (infile, outfile)[i]
            i += 1
            return retval

        with patch("os.path.isfile") as mock_isfile:
            with patch("builtins.open") as open_mock:
                mock_isfile.return_value = True
                open_mock.side_effect = return_conf
                update_service_conf({"test": {"new": "yes"}})

        self.assertEqual(outfile.captured,
                         "[fixed]\nold = no\n\n[test]\nnew = yes\n\n")

    def test_section_exists(self):
        """Tests that a setting is updated if the section exists."""
        infile = StringIO("[fixed]\nold = no\n")
        outfile = CapturingStringIO()

        i = 0

        def return_conf(path, *args, **kwargs):
            nonlocal i
            retval = (infile, outfile)[i]
            i += 1
            return retval

        with patch("builtins.open") as open_mock:
            open_mock.side_effect = return_conf
            update_service_conf({"fixed": {"old": "yes"}})

        self.assertEqual(outfile.captured, "[fixed]\nold = yes\n\n")


class WriteLicenseFileTestCase(TestCase):

    def test_from_file(self):
        """
        Tests that a license can be read from a file:// and written.
        """
        outfile = CapturingBytesIO()
        tempdir = TemporaryDirectory()
        license_file = os.path.join(tempdir.name, "license.txt")

        with open(license_file, "wb") as fp:
            fp.write(b"TEST LICENSE")

        orig_open = open

        def return_license(path, *args, **kwargs):
            if path.startswith("/etc/landscape"):
                return outfile
            else:
                return orig_open(path, *args, **kwargs)

        with patch("builtins.open") as open_mock:
            open_mock.side_effect = return_license
            with patch("settings_files.os") as os_mock:
                write_license_file(f"file://{license_file}", 1000, 1000)

        os_mock.chmod.assert_called_once_with(LICENSE_FILE, 0o640)
        os_mock.chown.assert_called_once_with(LICENSE_FILE, 1000, 1000)
        self.assertEqual(outfile.captured, b"TEST LICENSE")

        tempdir.cleanup()

    def test_from_url_URLError(self):
        """
        Tests that a LicenseFileReadException is raised if the license
        file is unreadable.
        """
        with patch("settings_files.urlopen") as urlopen_mock:
            urlopen_mock.side_effect = URLError("unreachable")
            self.assertRaises(
                LicenseFileReadException,
                write_license_file,
                "http://localhost2:12345/random",
                1000,
                1000,
            )

    def test_b64_encoded(self):
        """
        Tests that a license can be directly written from a b64-encoded
        bytestring.
        """
        outfile = CapturingBytesIO()
        license_bytes = b64encode(b"LICENSE").decode()

        with patch("builtins.open") as open_mock:
            open_mock.return_value = outfile
            with patch("settings_files.os") as os_mock:
                write_license_file(license_bytes, 1000, 1000)

        os_mock.chmod.assert_called_once_with(LICENSE_FILE, 0o640)
        os_mock.chown.assert_called_once_with(LICENSE_FILE, 1000, 1000)
        self.assertEqual(outfile.captured, b"LICENSE")

    def test_b64_error(self):
        """
        Tests that a LicenseFileReadException is raised if the license
        is invalid b64.
        """
        self.assertRaises(
            LicenseFileReadException,
            write_license_file,
            "notvalidb64haha",
            1000,
            1000,
        )


class WriteSSLCertTestCase(TestCase):

    def test_write(self):
        """
        Tests that we can write a b64-encoded string to the correct
        path.
        """
        outfile = CapturingBytesIO()

        with patch("builtins.open") as open_mock:
            open_mock.return_value = outfile
            write_ssl_cert(b64encode(b"SSL CERT").decode())

        self.assertEqual(outfile.captured, b"SSL CERT")

    def test_b64_error(self):
        """
        Tests that an SSLCertReadException is raised if the cert is
        invalid b64.
        """
        with patch("builtins.open"):
            self.assertRaises(
                SSLCertReadException,
                write_ssl_cert,
                "notvalidb64haha",
            )
