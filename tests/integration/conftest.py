"""
Integration test fixtures.
"""

import os
import pathlib

import jubilant
import pytest

CHARM_ARTIFACT_NAME = "landscape-server_ubuntu@22.04-amd64.charm"
"""
The name of the packed landscape-server charm.
"""


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
        "haproxy",
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
