from lib.tests.helpers import HookenvTest
from lib.tests.stubs import HostStub
from lib.tests.sample import SAMPLE_LEADER_DATA
from lib.relations.leader import LeaderRequirer, LeaderProvider


class LeaderProviderTest(HookenvTest):

    def setUp(self):
        super(LeaderProviderTest, self).setUp()
        self.host = HostStub()
        self.provider = LeaderProvider(hookenv=self.hookenv, host=self.host)

    def test_not_leader(self):
        """
        If the unit is not the leader, the LeaderProvider just no-ops.
        """
        self.hookenv.leader = False
        self.provider.provide_data()
        self.assertEqual({}, self.hookenv.leader_get())

    def test_fresh(self):
        """
        When run for the first time, the LeaderProvder class generates new
        leader data.
        """
        self.provider.provide_data()
        data = self.hookenv.leader_get()
        self.assertEqual(
            {"database-password": "landscape-sekret",
             "secret-token": "landscape-token",
             "leader-ip": "1.2.3.4"},
            data)

    def test_stored(self):
        """
        When run a second time, the LeaderProvider doesn't change previously
        generated data.
        """
        self.provider.provide_data()
        self.host.password = "new-password"
        self.host.secret_token = "new-token"
        self.provider.provide_data()
        data = self.hookenv.leader_get()
        self.assertEqual("landscape-sekret", data["database-password"])
        self.assertEqual("landscape-token", data["secret-token"])

    def test_leader_ip(self):
        """
        The leader-ip is refreshed if it changes.
        """
        self.provider.provide_data()
        assert self.hookenv.ip != "9.9.9.9", "Unexpected test precondition."
        self.hookenv.ip = "9.9.9.9"
        self.provider.provide_data()
        data = self.hookenv.leader_get()
        self.assertEqual("9.9.9.9", data["leader-ip"])


class LeaderRequirerTest(HookenvTest):

    def test_not_ready(self):
        """
        If not all the required keys are available, the LeaderRequirer is not
        ready.
        """
        requirer = LeaderRequirer(hookenv=self.hookenv)
        self.assertFalse(requirer)

    def test_ready(self):
        """
        If available, the LeaderRequirer holds the leader data.
        """
        self.hookenv.leader_set(SAMPLE_LEADER_DATA)
        requirer = LeaderRequirer(hookenv=self.hookenv)
        self.assertTrue(requirer)
        self.assertEqual(SAMPLE_LEADER_DATA, requirer["leader"])
