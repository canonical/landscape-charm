from yaml import dump
from fixtures import TempDir

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import ClusterStub, HostStub
from lib.tests.sample import SAMPLE_CLUSTER_UNIT_DATA
from lib.relations.landscape import LandscapeRelation, LandscapeLeaderContext
from lib.hook import HookError


class LandscapeRelationTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def setUp(self):
        super(LandscapeRelationTest, self).setUp()
        self.cluster = ClusterStub()
        self.host = HostStub()

    def test_required_keys(self):
        """
        The L{LandscapeRelation} class defines all keys that are required to
        be set on the cluster relation in order for the relation to be
        considered ready.
        """
        self.assertEqual(
            ["database-password"], LandscapeRelation.required_keys)

    def test_is_leader(self):
        """
        When the unit is the leader, the L{LandscapeRelation} automatically
        provides our local information, even if there's no other peer unit
        related with us.
        """
        relation = LandscapeRelation(cluster=self.cluster, host=self.host)
        self.assertTrue(relation.is_ready())
        self.assertEqual(SAMPLE_CLUSTER_UNIT_DATA, relation["leader"])
        self.assertEqual(SAMPLE_CLUSTER_UNIT_DATA, relation.provide_data())

    def test_is_not_leader(self):
        """
        When the unit is not the leader, it relies on the information provided
        by the remote unit acting as leader.
        """
        leader_data = SAMPLE_CLUSTER_UNIT_DATA.copy()
        leader_data["password"] = "remote-sekret"
        self.hookenv.relations = {
            "cluster": {
                "cluster:1": {
                    "landscape-client/1": leader_data,
                }
            }
        }
        self.cluster.leader = False
        relation = LandscapeRelation(cluster=self.cluster, host=self.host)
        self.assertTrue(relation.is_ready())
        self.assertEqual(leader_data, relation["leader"])
        self.assertEqual({}, relation.provide_data())

    def test_split_brain(self):
        """
        If we think to be the leader, but we also find a related peer unit that
        thinks to be the leader as well and has set the relation data, we raise
        an error.
        """
        unit_data = SAMPLE_CLUSTER_UNIT_DATA.copy()
        self.hookenv.relations = {
            "cluster": {
                "cluster:1": {
                    "landscape-client/1": unit_data,
                }
            }
        }
        self.assertRaises(
            HookError, LandscapeRelation, cluster=self.cluster, host=self.host)

    def test_not_ready(self):
        """
        This dependency manager is not considered ready if the leader data is
        not available.
        """
        self.cluster.leader = False
        relation = LandscapeRelation(cluster=self.cluster, host=self.host)
        self.assertFalse(relation.is_ready())


class LandscapeLeaderContextTest(HookenvTest):

    def setUp(self):
        super(LandscapeLeaderContextTest, self).setUp()
        self.host = HostStub()
        tempdir = self.useFixture(TempDir())
        self.path = tempdir.join("data")

    def test_fresh(self):
        """
        When created the for the first time, the L{LandscapeLeaderContext}
        class generates new data.
        """
        context = LandscapeLeaderContext(host=self.host, path=self.path)
        self.assertEqual({"database-password": "landscape-sekret"}, context)

    def test_stored(self):
        """
        When re-created, the L{LandscapeLeaderContext} class loads stored data.
        """
        with open(self.path, "w") as fd:
            fd.write(dump({"database-password": "old-sekret"}))
        context = LandscapeLeaderContext(host=self.host, path=self.path)
        self.assertEqual({"database-password": "old-sekret"}, context)
