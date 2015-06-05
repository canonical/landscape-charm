from lib.tests.helpers import HookenvTest
from lib.tests.sample import SAMPLE_HOSTED_DATA
from lib.relations.hosted import HostedRequirer, InvalidDeploymentModeError


class HostedRequirerTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The HostedRequirer class defines all keys that are required to
        be set on the cluster relation in order for the relation to be
        considered ready.
        """
        self.assertItemsEqual(
            ["deployment-mode"],
            HostedRequirer.required_keys)

    def test_not_related(self):
        """
        When the landscape-server service is not related to landscape-hosted
        the deployment-mode is standalone.
        """
        relation = HostedRequirer()
        self.assertTrue(relation.is_ready())
        self.assertEqual("standalone", SAMPLE_HOSTED_DATA["deployment-mode"])
        self.assertEqual([SAMPLE_HOSTED_DATA], relation["hosted"])

    def test_related(self):
        """
        When the landscape-server service is related to landscape-hosted
        the deployment-mode is the one set on the relation.
        """
        hosted_data = {"deployment-mode": "production"}
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        relation = HostedRequirer()
        self.assertTrue(relation.is_ready())
        self.assertEqual([hosted_data], relation["hosted"])

    def test_invalid_deployment_mode(self):
        """
        The deployment mode set on the relation must be a valid one, otherwise
        an error is raised.
        """
        hosted_data = {"deployment-mode": "foo"}
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        self.assertRaises(InvalidDeploymentModeError, HostedRequirer)
