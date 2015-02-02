from charmhelpers.core.services.helpers import RelationContext


class RabbitMQProvider(RelationContext):
    """Relation context for the `rabbitmq` interface."""
    name = "amqp"
    interface = "rabbitmq"
    required_keys = [
        "username",
        "vhost"]

    def provide_data(self):
        return {
            "username": "landscape",
            "vhost": "landscape",
        }


class RabbitMQRequirer(RelationContext):
    """Relation context for the `rabbitmq` interface."""
    name = "amqp"
    interface = "rabbitmq"
    required_keys = [
        "hostname",
        "password"]
