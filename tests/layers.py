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
    def testTearDown(cls):
        cls.environment.cleanUp()


class OneLandscapeUnitNoCronLayer(OneLandscapeUnitLayer):
    """Layer for all tests needing to run with the cron daemon stopped.

    The deployment has the same structure as OneLandscapeUnitLayer, the cron
    daemon will be stopped. Also, the layer setup waits for any currently
    running Landscape cron job to finish.
    """

    @classmethod
    def setUp(cls):
        cls.environment.stop_landscape_service("cron", restore=False)
        cls.environment.wait_landscape_cron_jobs()

    @classmethod
    def tearDown(cls):
        cls.environment.start_landscape_service("cron")


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


class TwoLandscapeUnitsLayer(OneLandscapeUnitLayer):
    """Layer for tests meant to run against a deployment with multiple units.

    The deployment will have one Juju unit of each needed Juju service,
    except for landscape-server, which will have two units.
    """

    @classmethod
    def setUp(cls):
        cls.environment.set_unit_count("landscape-server", 2)
        cls.leader, [cls.non_leader] = cls.environment.get_unit_ids(
            "landscape-server")


class LandscapeLeaderDestroyedLayer(TwoLandscapeUnitsLayer):

    @classmethod
    def setUp(cls):
        cls.environment.destroy_landscape_leader()
        cls.leader, _ = cls.environment.get_unit_ids(
            "landscape-server")
        cls.non_leader = None
