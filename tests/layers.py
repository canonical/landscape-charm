from helpers import EnvironmentFixture, get_config
from assets import b64_ssl_cert, b64_ssl_key


class OneLandscapeUnitLayer(object):
    """Layer for all tests meant to run against a minimal Landscape deployment.

    The deployment will have one Juju unit of each needed Juju service, with
    default configuration.
    """

    @classmethod
    def setUp(cls):
        cls.environment = EnvironmentFixture(config=get_config())
        cls.environment.setUp()

    @classmethod
    def tearDown(cls):
        cls.environment.cleanUp()


class OneLandscapeUnitCustomSSLCertificateLayer(OneLandscapeUnitLayer):
    """Layer for all tests needing a deployment with a custom SSL certificate.

    The deployment has the same structure as OneLandscapeUnitLayer, but a
    custom SSL certificate will be set on the landscape-service service, using
    the ssl-cert and ssl-key configuration options.
    """

    @classmethod
    def setUp(cls):
        cls.environment.configure_ssl(b64_ssl_cert(), b64_ssl_key())

    @classmethod
    def tearDown(cls):
        cls.environment.configure_ssl("", "")
