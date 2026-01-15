#!/bin/bash
set -eux

OFFER_NAME="${OFFER_NAME:-"admin/lbaas.haproxy"}"
MODEL_NAME="${MODEL_NAME:-"landscape-charm-build"}"
OFFER_APP_NAME="${OFFER_APP_NAME:-"saas-haproxy"}"

# Consume the LBaaS `haproxy-route` offer
juju consume "${OFFER_NAME}" -m "${MODEL_NAME}" "${OFFER_APP_NAME}"

# Integrate it with the Ingress Configurators
juju integrate -m "${MODEL_NAME}" "$OFFER_APP_NAME:haproxy-route" "http-ingress:haproxy-route"
juju integrate -m "${MODEL_NAME}" "$OFFER_APP_NAME:haproxy-route" "https-ingress:haproxy-route"
juju integrate -m "${MODEL_NAME}" "$OFFER_APP_NAME:haproxy-route" "hostagent-messenger-ingress:haproxy-route"
juju integrate -m "${MODEL_NAME}" "$OFFER_APP_NAME:haproxy-route" "ubuntu-installer-attach-ingress:haproxy-route"
