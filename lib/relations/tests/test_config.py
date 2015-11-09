from lib.tests.helpers import HookenvTest
from lib.tests.stubs import PsutilStub
from lib.relations.config import (
    ConfigRequirer, OpenIDConfigurationError, RootUrlNotValidError)


class ConfigRequirerTest(HookenvTest):

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
        self.assertEqual("https://example.com/", result["config"]["root-url"])

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

    def test_worker_counts_defaults(self):
        """
        Default values for worker-counts are 2 per each service.
        """
        result = ConfigRequirer(hookenv=self.hookenv)
        self.assertEqual(
            {"appserver": 2, "pingserver": 2, "message-server": 2},
            result["config"]["worker-counts"])

    def test_worker_counts_minimum(self):
        """
        Calculating worker counts returns a minimum of 1 even if
        less than 1 is requested.
        """
        self.hookenv.config().update({"worker-counts": -2})
        result = ConfigRequirer(hookenv=self.hookenv)
        self.assertEqual(
            {"appserver": 1, "pingserver": 1, "message-server": 1},
            result["config"]["worker-counts"])

    def test_worker_counts_maximum(self):
        """
        Calculating worker counts returns a maximum of 9 even if more
        is asked for.
        """
        self.hookenv.config().update({"worker-counts": 10})
        result = ConfigRequirer(hookenv=self.hookenv)
        self.assertEqual(
            {"appserver": 9, "pingserver": 9, "message-server": 9},
            result["config"]["worker-counts"])

    def test_worker_counts_scaling(self):
        """
        Calculating worker counts returns a number of processes each
        service should use depending on the number of CPU cores and memory.

        For each extra core and GB of memory, one process is added to the
        minimum of 1.
        """
        # Turn auto-scaling on.
        self.hookenv.config().update({"worker-counts": 0})
        psutil_stub = PsutilStub(num_cpus=2, physical_memory=2*1024**3)
        result = ConfigRequirer(hookenv=self.hookenv, psutil=psutil_stub)
        self.assertEqual(
            {"appserver": 3, "pingserver": 3, "message-server": 3},
            result["config"]["worker-counts"])

    def test_worker_counts_cpu_scaling(self):
        """
        Calculating worker counts scales with CPU cores.
        """
        # Turn auto-scaling on.
        self.hookenv.config().update({"worker-counts": 0})
        # For each CPU core after the second, one process is added.
        psutil_stub = PsutilStub(num_cpus=4, physical_memory=1*1024**3)
        result = ConfigRequirer(hookenv=self.hookenv, psutil=psutil_stub)
        self.assertEqual(
            {"appserver": 4, "pingserver": 4, "message-server": 4},
            result["config"]["worker-counts"])

    def test_worker_counts_memory_scaling(self):
        """
        Calculating worker counts scales with total physical memory.
        """
        # Turn auto-scaling on.
        self.hookenv.config().update({"worker-counts": 0})
        # For each extra 1GB of RAM after 1GB, one process is added.
        psutil_stub = PsutilStub(num_cpus=1, physical_memory=4*1024**3)
        result = ConfigRequirer(hookenv=self.hookenv, psutil=psutil_stub)
        self.assertEqual(
            {"appserver": 4, "pingserver": 4, "message-server": 4},
            result["config"]["worker-counts"])
