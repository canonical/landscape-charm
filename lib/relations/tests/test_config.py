from lib.tests.helpers import HookenvTest
from lib.relations.config import (
    ConfigRequirer, OpenIDConfigurationError, RootUrlNotValidError)


class ServicesHookTest(HookenvTest):

    def test_root_url_is_set_and_invalid(self):
        """
        If an invalid root-url config option is set, a ConfigError is raised.
        """
        self.hookenv.config().update({"root-url": "asd"})

        with self.assertRaises(RootUrlNotValidError) as error:
            ConfigRequirer(hookenv=self.hookenv)

        expected = (
            "The 'root-url' configuration value is not a valid URL. "
            "Please make sure it is of the form 'http[s]://<hostname>/'")
        self.assertEqual(expected, error.exception.message)

    def test_root_url_is_set_without_protocol(self):
        """
        If an invalid root-url config option is set without a protocol, a
        ConfigError is raised.
        """
        self.hookenv.config().update({"root-url": "example.com/"})

        with self.assertRaises(RootUrlNotValidError) as error:
            ConfigRequirer(hookenv=self.hookenv)

        expected = (
            "The 'root-url' configuration value is not a valid URL. "
            "Please make sure it is of the form 'http[s]://<hostname>/'")
        self.assertEqual(expected, error.exception.message)

    def test_root_url_is_set_without_trailing_slash(self):
        """
        If an invalid root-url config option is set without a trailing slash,
        a ConfigError is raised.
        """
        self.hookenv.config().update({"root-url": "https://example.com"})
        with self.assertRaises(RootUrlNotValidError) as error:
            ConfigRequirer(hookenv=self.hookenv)

        expected = (
            "The 'root-url' configuration value is not a valid URL. "
            "Please make sure it is of the form 'http[s]://<hostname>/'")
        self.assertEqual(expected, error.exception.message)

    def test_a_valid_root_url_configuration_key_is_set(self):
        """No excpetion is raised if the root-url config entry is valid.

        The resulting ConfigRequirer is a dict with a "config" entry that
        matches the contents of the config passed.
        """
        self.hookenv.config().update({"root-url": "https://example.com/"})
        result = ConfigRequirer(hookenv=self.hookenv)
        self.assertEqual({"config": {"root-url": "https://example.com/"}},
                         result)

    def test_openid_options_provider_missing(self):
        """
        If openid_provider_url option is provided but not openid_logout_url,
        an error is raised.
        """
        self.hookenv.config().update({"openid-provider-url": "blah"})

        with self.assertRaises(OpenIDConfigurationError) as error:
            ConfigRequirer(hookenv=self.hookenv)

        expected = (
            "To set up OpenID authentication, both 'openid-provider-url' "
            "and 'openid-logout-url' must be provided.")
        self.assertEqual(expected, error.exception.message)

    def test_openid_options_logout_missing(self):
        """
        If openid_logout_url option is provided but not openid_provider_url,
        an error is raised.
        """
        self.hookenv.config().update({"openid-logout-url": "blah"})

        with self.assertRaises(OpenIDConfigurationError) as error:
            ConfigRequirer(hookenv=self.hookenv)

        expected = (
            "To set up OpenID authentication, both 'openid-provider-url' "
            "and 'openid-logout-url' must be provided.")
        self.assertEqual(expected, error.exception.message)
