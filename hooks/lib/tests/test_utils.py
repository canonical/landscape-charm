import unittest

from lib.utils import is_valid_url


class IsValidURLTestCase(unittest.TestCase):

    def test_missing_trailing_slash(self):
        """No trailing slash means the URL is invalid for root-url."""
        self.assertFalse(is_valid_url("https://google.com"))

    def test_missing_protocol(self):
        """A protocol (http or https) is needed for a URL to be a valid
        root-url."""
        self.assertFalse(is_valid_url("ftp://google.com/"))

    def test_http_or_https_protocol(self):
        """The URL for the root-url should have either http or https as a
        protocol."""
        self.assertTrue(is_valid_url("http://google.com/"))
        self.assertTrue(is_valid_url("https://google.com/"))

    def test_missing_protocol_delimiter(self):
        """We need the URL to have the protocol field"""
        self.assertFalse(is_valid_url("httpisawesome.com/"))

    def test_correct_url_is_validated(self):
        """A "correct" URL is validated by the is_valid_url function."""
        self.assertTrue(is_valid_url("http://example.com:9090/blah/"))
