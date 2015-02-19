from charmhelpers.core.services.helpers import RelationContext


class RabbitMQProvider(RelationContext):
    """Relation data provider feeding rabbitmq our vhost and username."""
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
    """Relation data requirer getting auth details from rabbitmq."""
    name = "amqp"
    interface = "rabbitmq"
    required_keys = [
        "hostname",
        "password"]
