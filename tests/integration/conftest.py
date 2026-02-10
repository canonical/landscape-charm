"""
Integration test fixtures.
"""

import os
import pathlib
import uuid

import jubilant
import pytest

from tests.integration.helpers import _has_haproxy_route_relation

BUNDLE_NAME = "bundle.yaml"
"""
The name of the bundle used for integration testing.
"""


WAIT_TIMEOUT_SECONDS = 60 * 20  # Landscape takes a long time to deploy.


USE_HOST_JUJU_MODEL = os.getenv("LANDSCAPE_CHARM_USE_HOST_JUJU_MODEL") or False
"""
If `True`, return a reference the current Juju model on the host instead of a temporary
model.
"""

USE_HOST_LBAAS_MODEL = os.getenv("LANDSCAPE_CHARM_USE_HOST_LBAAS_MODEL") or False
"""
If `True`, use existing lbaas model instead of creating a temporary one.
The model name should be set in LBAAS_MODEL_NAME environment variable.
"""

LBAAS_MODEL_NAME = os.getenv("LBAAS_MODEL_NAME", "lbaas")
"""
Name of the lbaas model to use when USE_HOST_LBAAS_MODEL is True.
"""


@pytest.fixture(scope="module")
def host_juju():
    """
    Get a reference to the current Landscape server Juju model on the host.

    This runs a light check to ensure the current model is in fact a Landscape server
    bundle.

    This fixture is useful when experimenting with new tests to avoid needing to
    re-deploy the bundle in between attempts.
    """
    yield _host_juju()


def _host_juju():
    juju = jubilant.Juju()
    expected_applications = {
        "landscape-server",
        "postgresql",
        "rabbitmq-server",
    }
    model_applications = juju.status().apps

    for app in expected_applications:
        assert app in model_applications

    return juju


@pytest.fixture(scope="module")
def juju():
    """
    Create a temporary Juju model.
    """

    if USE_HOST_JUJU_MODEL:
        yield _host_juju()
    else:
        with jubilant.temp_model() as juju:
            yield juju


@pytest.fixture(scope="module")
def bundle(juju: jubilant.Juju) -> None:
    """
    Create a Landscape bundle, using a local landscape-server charm.

    The landscape-server charm must be packed out-of-band; this fixture will not pack
    the charm itself.
    """
    if not USE_HOST_JUJU_MODEL:
        juju.deploy(charm=bundle_path())
        juju.wait(
            jubilant.all_active,
            timeout=WAIT_TIMEOUT_SECONDS,
            successes=5,  # Landscape can take a while to come up, fully active.
            delay=5.0,
        )


def bundle_path() -> pathlib.Path:
    """
    Return the full absolute path to the landscape-server integration test bundle.
    """
    path = pathlib.Path(__file__).parent / BUNDLE_NAME
    assert path.exists(), f"{path} not found."
    return path


@pytest.fixture(scope="module")
def lbaas(juju: jubilant.Juju):
    """
    Set up external HAProxy in a separate lbaas model for LBaaS testing.

    This fixture can either:
    - Use an existing lbaas model (if USE_HOST_LBAAS_MODEL is True)
    - Create a temporary model and deploy haproxy + self-signed-certificates

    Environment variables:
    - LANDSCAPE_CHARM_USE_HOST_LBAAS_MODEL: Set to use existing lbaas deployment
    - LBAAS_MODEL_NAME: Name of the lbaas model (default: "lbaas")
    """
    status = juju.status()
    app_status = status.apps.get("landscape-server")

    if not app_status or any(
        x not in app_status.relations
        for x in [
            "http-ingress",
            "ubuntu-installer-attach-ingress",
            "hostagent-messenger-ingress",
        ]
    ):
        pytest.skip("Ingress not configured, skipping...")

    if USE_HOST_LBAAS_MODEL:
        lbaas_model = LBAAS_MODEL_NAME
        lbaas_juju = jubilant.Juju(model=lbaas_model)

        try:
            lbaas_status = lbaas_juju.status()
            assert "haproxy" in lbaas_status.apps, "haproxy not found in lbaas model"
            assert (
                "self-signed-certificates" in lbaas_status.apps
            ), "self-signed-certificates not found in lbaas model"
        except Exception as e:
            pytest.fail(
                f"Failed to connect to existing lbaas model '{lbaas_model}': {e}"
            )

        yield lbaas_juju
    else:
        lbaas_model = str(uuid.uuid4())

        juju.add_model(lbaas_model)
        lbaas_juju = jubilant.Juju(model=lbaas_model)

        try:
            lbaas_juju.deploy("haproxy", channel="2.8/edge")
            lbaas_juju.config(
                "haproxy",
                values={"external-hostname": "landscape.local", "enable-hsts": "false"},
            )
            lbaas_juju.deploy("self-signed-certificates", channel="1/stable")
            lbaas_juju.wait(jubilant.all_active, timeout=600)

            lbaas_juju.integrate(
                "haproxy:certificates", "self-signed-certificates:certificates"
            )
            lbaas_juju.wait(jubilant.all_active, timeout=300)

            lbaas_juju.offer(endpoint="haproxy:haproxy-route")

            offer_app_name = "lbaas-haproxy"
            juju.consume(f"admin/{lbaas_model}.haproxy", offer_app_name)

            juju.integrate(
                f"{offer_app_name}:haproxy-route", "http-ingress:haproxy-route"
            )
            juju.wait(
                lambda status: _has_haproxy_route_relation(juju, "http-ingress"),
                timeout=300,
            )

            juju.integrate(
                f"{offer_app_name}:haproxy-route",
                "hostagent-messenger-ingress:haproxy-route",
            )
            juju.wait(
                lambda status: _has_haproxy_route_relation(
                    juju, "hostagent-messenger-ingress"
                ),
                timeout=300,
            )

            juju.integrate(
                f"{offer_app_name}:haproxy-route",
                "ubuntu-installer-attach-ingress:haproxy-route",
            )
            juju.wait(
                lambda status: _has_haproxy_route_relation(
                    juju, "ubuntu-installer-attach-ingress"
                ),
                timeout=300,
            )

            juju.wait(jubilant.all_active, timeout=600)

            yield lbaas_juju
        finally:
            juju.destroy_model(lbaas_model, destroy_storage=True, force=True)
