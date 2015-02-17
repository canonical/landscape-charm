from lib.tests.helpers import HookenvTest
from lib.relations.rabbitmq import RabbitMQProvider, RabbitMQRequirer


class RabbitMQProviderTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The RabbitMQProvider class defines all keys that are required to
        be set on the db relation in order for the relation to be considered
        ready.
        """
        self.assertEqual(
            ["username", "vhost"], RabbitMQProvider.required_keys)

    def test_provide_data(self):
        """
        The RabbitMQProvider class feeds rabbitmq with the vhost and username
        that Landscape requires.
        """
        relation = RabbitMQProvider()
        self.assertEqual(
            {"username": "landscape", "vhost": "landscape"},
            relation.provide_data())


class RabbitMQRequirerTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The RabbitMQRequirer class defines all keys that are required to
        be set on the db relation in order for the relation to be considered
        ready.
        """
        self.assertEqual(
            ["hostname", "password"], RabbitMQRequirer.required_keys)
