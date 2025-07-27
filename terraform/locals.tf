locals {
  legacy_amqp = var.channel != "latest-stable/edge" || var.revision <= 141
  # Needed since the relations changed to support the hostagent services after 141 on latest-stable/edge
  amqp_relations = local.legacy_amqp ? { amqp = "amqp" } : { inbound_amqp = "inbound-amqp", outbound_amqp = "outbound-amqp" }
}
