from yaml import dump
from fixtures import TempDir

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import HostStub
from lib.tests.sample import SAMPLE_LEADER_CONTEXT_DATA
from lib.relations.landscape import (
    LandscapeRequirer, LandscapeProvider, LandscapeLeaderContext)
from lib.hook import HookError


class LandscapeRequirerTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The L{LandscapeRequirer} class defines all keys that are required to
        be set on the cluster relation in order for the relation to be
        considered ready.
        """
        self.assertItemsEqual(
            ["database-password", "secret-token", "leader-ip"],
            LandscapeRequirer.required_keys)

    def test_is_leader(self):
        """
        When the unit is the leader, the L{LandscapeRequirer} automatically
        provides our local information, even if there's no other peer unit
        related with us.
        """
        relation = LandscapeRequirer(SAMPLE_LEADER_CONTEXT_DATA)
        self.assertTrue(relation.is_ready())
        self.assertEqual(SAMPLE_LEADER_CONTEXT_DATA, relation["leader"])

    def test_is_not_leader(self):
        """
        When the unit is not the leader, it relies on the information provided
        by the remote unit acting as leader.
        """
        leader_data = SAMPLE_LEADER_CONTEXT_DATA.copy()
        leader_data["password"] = "remote-sekret"
        self.hookenv.relations = {
            "cluster": {
                "cluster:1": {
                    "landscape-client/1": leader_data,
                }
            }
        }
        relation = LandscapeRequirer(None)
        self.assertTrue(relation.is_ready())
        self.assertEqual(leader_data, relation["leader"])

    def test_split_brain(self):
        """
        If we think to be the leader, but we also find a related peer unit that
        thinks to be the leader as well and has set the relation data, we raise
        an error.
        """
        unit_data = SAMPLE_LEADER_CONTEXT_DATA.copy()
        self.hookenv.relations = {
            "cluster": {
                "cluster:1": {
                    "landscape-client/1": unit_data,
                }
            }
        }
        self.assertRaises(
            HookError, LandscapeRequirer, SAMPLE_LEADER_CONTEXT_DATA)

    def test_not_ready(self):
        """
        This dependency manager is not considered ready if the leader data is
        not available.
        """
        relation = LandscapeRequirer(None)
        self.assertFalse(relation.is_ready())


class LandscapeProviderTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The L{LandscapeProvider} class defines all keys that are required to
        be set before we actually modify the relation.
        """
        self.assertItemsEqual(
            ["database-password", "secret-token", "leader-ip"],
            LandscapeProvider.required_keys)

    def test_provide_data(self):
        """
        The L{LandscapeProvider} data provider returns the leader context data
        if available (i.e. if we are the leader).
        """
        relation = LandscapeProvider(SAMPLE_LEADER_CONTEXT_DATA)
        self.assertEqual(SAMPLE_LEADER_CONTEXT_DATA, relation.provide_data())

    def test_provide_data_not_leader(self):
        """
        The L{LandscapeProvider} data provider returns an empty C{dict} if no
        leader context is available (i.e. we're not the leader).
        """
        relation = LandscapeProvider(None)
        self.assertEqual({}, relation.provide_data())


class LandscapeLeaderContextTest(HookenvTest):

    def setUp(self):
        super(LandscapeLeaderContextTest, self).setUp()
        self.host = HostStub()
        tempdir = self.useFixture(TempDir())
        self.path = tempdir.join("data")

    def test_fresh(self):
        """
        When created for the first time, the L{LandscapeLeaderContext} class
        generates new data.
        """
        context = LandscapeLeaderContext(host=self.host, path=self.path,
                                         hookenv=self.hookenv)
        self.assertItemsEqual(
            ["database-password", "secret-token", "leader-ip"], context.keys())
        self.assertEqual("landscape-sekret", context["database-password"])
        self.assertEqual("landscape-token", context["secret-token"])
        # The IP is coming from the HookenvStub class used by self.hookenv
        self.assertEqual("1.2.3.4", context["leader-ip"])

    def test_stored(self):
        """
        When re-created, the L{LandscapeLeaderContext} class loads stored data.
        """
        with open(self.path, "w") as fd:
            fd.write(dump({"database-password": "old-sekret",
                           "secret-token": "old-token",
                           "leader-ip": "old-ip"}))
        context = LandscapeLeaderContext(
                host=self.host, path=self.path, hookenv=self.hookenv)
        self.assertEqual({"database-password": "old-sekret",
                          "secret-token": "old-token",
                          "leader-ip": "old-ip"}, context)
