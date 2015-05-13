from helpers import EnvironmentFixture, get_config


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
