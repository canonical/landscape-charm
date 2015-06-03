from fixtures import TestWithFixtures

from lib.tests.helpers import TempExecutableFile
from lib import cluster


class ClusterTest(TestWithFixtures):

    def setUp(self):
        self.is_leader = self.useFixture(TempExecutableFile("is-leader"))

    def test_elected_leader_true(self):
        self.is_leader.set_output("true", args=["--format", "json"])
        self.assertTrue(
            cluster.is_elected_leader(None, is_leader_exec=self.is_leader.path))

    def test_elected_leader_false(self):
        self.is_leader.set_output("false", args=["--format", "json"])
        self.assertFalse(
            cluster.is_elected_leader(None, is_leader_exec=self.is_leader.path))
