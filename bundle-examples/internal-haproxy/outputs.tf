output "lbaas_model_name" {
  value = juju_model.lbaas_model.name
}

output "lbaas_model_uuid" {
  value = juju_model.lbaas_model.id
}

output "haproxy_offer_url" {
  value = juju_offer.haproxy_route.url
}

output "haproxy_application" {
  value = juju_application.haproxy.name
}
