from unittest import TestCase

from charmhelpers.core.services.base import ServiceManager

from lib.utils import is_valid_url, get_required_data, update_persisted_data
from lib.tests.helpers import HookenvTest


class IsValidURLTest(TestCase):

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


class GetRequiredDataTest(HookenvTest):

    with_hookenv_monkey_patching = True

    def setUp(self):
        super(GetRequiredDataTest, self).setUp()
        self.services = [{"service": "foo", "required_data": []}]
        self.manager = ServiceManager(services=self.services)

    def test_find_matching(self):
        """
        The get_required_data function returns the matching required_data
        entry.
        """
        required_data = self.manager.get_service("foo")["required_data"]
        required_data.extend([{"bar": "egg"}, {"baz": "yuk"}])
        self.assertEqual("egg", get_required_data(self.manager, "foo", "bar"))

    def test_no_match(self):
        """
        The get_required_data function returns None if no match is found.
        """
        self.assertIsNone(get_required_data(self.manager, "foo", "bar"))


class UpdatePersistedDataTest(HookenvTest):

    def test_fresh(self):
        """
        When a key is set for the first time, None is returned.
        """
        self.assertIsNone(
            update_persisted_data("foo", "bar", hookenv=self.hookenv))

    def test_replace(self):
        """
        When a key is set again to a new value, the old value is returned.
        """
        update_persisted_data("foo", "bar", hookenv=self.hookenv)
        self.assertEqual(
            "bar", update_persisted_data("foo", "bar", hookenv=self.hookenv))
