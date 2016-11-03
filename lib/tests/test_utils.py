from unittest import TestCase

from charmhelpers.core import hookenv
from charmhelpers.core.services.base import ServiceManager

from lib.error import CharmError
from lib.utils import (is_valid_url, get_required_data, update_persisted_data,
                       get_archive_url, CommandRunner)
from lib.tests.helpers import HookenvTest
from lib.tests.stubs import SubprocessStub


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


class GetArchiveUrlTest(TestCase):

    def test_no_root_url(self):
        """When root-url is not set, returns "/archive"."""
        self.assertEqual("/archive", get_archive_url({}))

    def test_simple_root_url(self):
        """When root-url is set to a hostname, prepends "archive." to it."""
        self.assertEqual(
            "https://archive.landscape.canonical.com/",
            get_archive_url({"root-url": "https://landscape.canonical.com/"}))

    def test_all_url_components(self):
        """
        When root-url is set to a URL with query string etc. "archive." is
        still prepended and all the other components of the URL are kept.
        """
        self.assertEqual(
            "http://archive.test:8080/some/path;param?arg=yes#top",
            get_archive_url(
                {"root-url": "http://test:8080/some/path;param?arg=yes#top"}))


class CommandRunnerTest(HookenvTest):

    CMD = '/bin/some-command'
    ARGS = ('x', 'y', 'z')
    SCRIPT = CMD + ' ' + ' '.join(ARGS)

    def setUp(self):
        super(CommandRunnerTest, self).setUp()
        self.subprocess = SubprocessStub()
        self.subprocess.add_fake_executable(self.CMD)
        self.subprocess.add_fake_executable(self.CMD, self.ARGS)
        self.subprocess.add_fake_script(self.SCRIPT)
        self.runner = CommandRunner(self.hookenv, self.subprocess)

    def test_run_with_args(self):
        """Make sure everything's fine when we pass in args."""
        self.runner.run(self.CMD, 'x', 'y', 'z')

        self.assertEqual(self.subprocess.calls,
                         [([self.CMD, 'x', 'y', 'z'], {}),
                          ])

    def test_run_without_args(self):
        """Make sure everything's fine even with no args."""
        self.runner.run(self.CMD)

        self.assertEqual(self.subprocess.calls,
                         [([self.CMD], {}),
                          ])

    def test_run_in_dir(self):
        """Check the behavior of running a command in a directory."""
        runner = self.runner.in_dir('/tmp')

        runner.run(self.CMD)

        self.assertEqual(self.subprocess.calls,
                         [([self.CMD], {'cwd': '/tmp'}),
                          ])

    def test_run_logging(self):
        """Make sure that the command gets logged."""
        self.runner.run(self.CMD, 'x', 'y', 'z')

        self.assertEqual(self.hookenv.messages,
                         [('running \'/bin/some-command x y z\'',
                           hookenv.DEBUG),
                          ])

    def test_run_failure(self):
        """Make sure that failures are properly handled.

        "properly handled" includes logging.
        """
        self.subprocess.add_fake_executable(self.CMD, self.ARGS, return_code=1)

        with self.assertRaises(CharmError) as cm:
            self.runner.run(self.CMD, 'x', 'y', 'z')

        self.assertEqual(str(cm.exception),
                         'command failed (see unit logs): '
                         '/bin/some-command x y z')
        self.assertEqual(self.hookenv.messages,
                         [('running \'/bin/some-command x y z\'',
                           hookenv.DEBUG),
                          ('got return code 1 running '
                           '\'/bin/some-command x y z\'',
                           hookenv.ERROR),
                          ])

    def test_shell_subprocess_calls(self):
        """Make sure we get the correct subprocess calls."""
        self.runner.shell(self.SCRIPT)

        self.assertEqual(self.subprocess.calls,
                         [(self.SCRIPT, {'shell': True}),
                          ])

    def test_shell_in_dir(self):
        """Check the behavior of running a command in a directory."""
        runner = self.runner.in_dir('/tmp')

        runner.shell(self.SCRIPT)

        self.assertEqual(self.subprocess.calls,
                         [(self.SCRIPT, {'cwd': '/tmp', 'shell': True}),
                          ])

    def test_shell_logging(self):
        """Make sure that the command gets logged."""
        self.runner.shell(self.SCRIPT)

        self.assertEqual(self.hookenv.messages,
                         [('running \'/bin/some-command x y z\'',
                           hookenv.DEBUG),
                          ])

    def test_shell_failure(self):
        """Make sure that failures are properly handled.

        "properly handled" includes logging.
        """
        self.subprocess.add_fake_script(self.SCRIPT, return_code=1)

        with self.assertRaises(CharmError) as cm:
            self.runner.shell(self.SCRIPT)

        self.assertEqual(str(cm.exception),
                         'command failed (see unit logs): '
                         '/bin/some-command x y z')
        self.assertEqual(self.subprocess.calls,
                         [(self.SCRIPT, {'shell': True}),
                          ])
        self.assertEqual(self.hookenv.messages,
                         [('running \'/bin/some-command x y z\'',
                           hookenv.DEBUG),
                          ('got return code 1 running '
                           '\'/bin/some-command x y z\'',
                           hookenv.ERROR),
                          ])
