from fixtures import TestWithFixtures

from lib import cluster
from lib.tests.stubs import SubprocessStub


class ClusterTest(TestWithFixtures):
    def setUp(self):
        self.subprocess = SubprocessStub()

    def test_is_elected_leader_true(self):
        """
        If the 'is-leader' command returns 'true', is_elected_leader()
        returns True.
        """
        def is_leader_true(args, **kwargs):
            if args == ["--format", "json"]:
                return 0, "true", ""

        self.subprocess.add_fake_executable("is-leader", is_leader_true)
        self.assertTrue(
            cluster.is_elected_leader(None, subprocess=self.subprocess))

    def test_is_elected_leader_false(self):
        """
        If the 'is-leader' command returns 'false', is_elected_leader()
        returns False.
        """
        def is_leader_false(args, **kwargs):
            if args == ["--format", "json"]:
                return 0, "false", ""

        self.subprocess.add_fake_executable("is-leader", is_leader_false)
        self.assertFalse(
            cluster.is_elected_leader(None, subprocess=self.subprocess))
