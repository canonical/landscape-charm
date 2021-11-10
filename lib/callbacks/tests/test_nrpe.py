from charmhelpers.core.services.base import ServiceManager

from lib.tests.helpers import HookenvTest
from lib.tests.stubs import NrpeConfigStub
from lib.callbacks.nrpe import (
    ConfigureNRPE,
    DEFAULT_SERVICES,
    LEADER_SERVICES)


class ConfigureNRPETest(HookenvTest):
    def setUp(self):
        super(ConfigureNRPETest, self).setUp()
        self.manager = ServiceManager([])
        self.fake_nrpe = NrpeConfigStub()
        self.callback = ConfigureNRPE(hookenv=self.hookenv,
                                      nrpe_config=self.fake_nrpe)

    def test_add_nrpe_check(self):
        """Test adding NRPE checks."""
        config = self.hookenv.config()
        config["nagios_context"] = "juju"
        self.hookenv.relations['nrpe-external-master'] = {"id": "1"}
        self.callback(self.manager, None, None)
        nrpe_checks = self.fake_nrpe.get_nrpe_checks()
        for svc in DEFAULT_SERVICES:
            self.assertIn(svc, nrpe_checks)
        for svc in LEADER_SERVICES:
            self.assertIn(svc, nrpe_checks)

    def test_remove_nrpe_check(self):
        config = self.hookenv.config()
        config["nagios_context"] = "juju"
        self.callback(self.manager, None, None)
        nrpe_checks = self.fake_nrpe.get_nrpe_checks()
        self.assertTrue(len(nrpe_checks) == 0)
