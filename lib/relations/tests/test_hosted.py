from lib.tests.helpers import HookenvTest
from lib.tests.sample import SAMPLE_HOSTED_DATA
from lib.relations.hosted import (
    DuplicateArchiveNameError, HostedRequirer, InvalidDeploymentModeError,
    MissingSupportedReleaseUrlError)


class HostedRequirerTest(HookenvTest):

    with_hookenv_monkey_patch = True

    def test_required_keys(self):
        """
        The HostedRequirer class defines all keys that are required to
        be set on the cluster relation in order for the relation to be
        considered ready.
        """
        self.assertItemsEqual(
            ["deployment-mode", "ppas-to-proxy", "supported-releases",
             "gpg-passphrase-path", "gpg-home-path"],
            HostedRequirer.required_keys)

    def test_not_related(self):
        """
        When the landscape-server service is not related to landscape-hosted
        the deployment-mode is standalone.
        """
        relation = HostedRequirer({"config": {}})
        self.assertTrue(relation.is_ready())
        self.assertEqual("standalone", SAMPLE_HOSTED_DATA["deployment-mode"])
        self.assertEqual([SAMPLE_HOSTED_DATA], relation["hosted"])

    def test_related(self):
        """
        When the landscape-server service is related to landscape-hosted
        the deployment-mode is the one set on the relation.
        """
        hosted_data = {
            "deployment-mode": "production",
            "supported-releases": "16.03",
            "ppas-to-proxy": "16.03=http://foo/16.03/ubuntu",
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg"}
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        relation = HostedRequirer({"config": {}})
        self.assertTrue(relation.is_ready())
        self.assertEqual([hosted_data], relation["hosted"])

    def test_related_but_not_ready(self):
        """
        When the landscape-server service is related to landscape-hosted but
        the remote landscape-hosted unit still has to pop up, the relation
        is not ready.
        """
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {}
            }
        }
        relation = HostedRequirer({"config": {}})
        self.assertFalse(relation.is_ready())

    def test_invalid_deployment_mode(self):
        """
        The deployment mode set on the relation must be a valid one, otherwise
        an error is raised.
        """
        hosted_data = {
            "deployment-mode": "foo",
            "supported-releases": "16.03",
            "ppas-to-proxy": "16.03=http://foo/16.03/ubuntu",
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg",
        }
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        with self.assertRaises(InvalidDeploymentModeError) as error:
            HostedRequirer({"config": {}})

        self.assertEqual(
            "Invalid deployment-mode 'foo'", error.exception.message)

    def test_get_data_pppa_proxy(self):
        """
        Hosted relation data "ppas-to-proxy" is parsed into a dict,
        and "supported-releases" is parsed into a list.
        """
        hosted_data = {
            "deployment-mode": "edge",
            "supported-releases": "16.03, 16.06",
            "ppas-to-proxy": (
                "16.03=http://foo/16.03/ubuntu,16.06=http://foo/16.06/ubuntu"),
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg",
        }
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        relation = HostedRequirer({"config": {}})
        self.assertEqual(
            {"16.03": "http://foo/16.03/ubuntu",
             "16.06": "http://foo/16.06/ubuntu"},
            relation["hosted"][0]["ppas-to-proxy"])
        self.assertEqual(["16.03", "16.06"],
                         relation["hosted"][0]["supported-releases"])

    def test_duplicate_archive_name(self):
        """
        Specifying the same short name for a PPA in ppas-to-proxy throws
        an exception.
        """
        hosted_data = {
            "deployment-mode": "edge",
            "supported-releases": "16.03",
            "ppas-to-proxy": (
                "16.03=http://foo/16.03/ubuntu,16.03=http://foo/16.06/ubuntu"),
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg",
        }
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        with self.assertRaises(DuplicateArchiveNameError) as error:
            HostedRequirer({"config": {}})

        self.assertEqual(
            "Archive name '16.03' used twice in ppas-to-proxy.",
            error.exception.message)

    def test_missing_supported_release(self):
        """
        A release is listed in supported-releases but the URL for it is not
        provided in ppas-to-proxy attribute of the hosted relation data.
        """
        hosted_data = {
            "deployment-mode": "edge",
            "supported-releases": "16.06,16.09",
            "ppas-to-proxy": "16.03=http://foo/16.03/ubuntu",
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg",
        }
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        with self.assertRaises(MissingSupportedReleaseUrlError) as error:
            HostedRequirer({"config": {}})

        self.assertEqual(
            ("Some archives (16.06, 16.09) listed in 'supported-releases' do "
             "not have their URLs defined in 'ppas-to-proxy'."),
            error.exception.message)

    def test_archive_url(self):
        """
        When the landscape-server service is related to landscape-hosted
        the archive-url is the one set on the relation.
        """
        hosted_data = {
            "deployment-mode": "production",
            "supported-releases": "16.03",
            "ppas-to-proxy": "16.03=http://foo/16.03/ubuntu",
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg"}
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        relation = HostedRequirer({"config": {}})
        self.assertEqual("/archive", relation["hosted"][0]["archive-url"])

    def test_archive_url_from_root_url(self):
        """
        When the landscape-server service is related to landscape-hosted
        the archive-url is set based on the root-url from configuration.
        """
        hosted_data = {
            "deployment-mode": "production",
            "supported-releases": "16.03",
            "ppas-to-proxy": "16.03=http://foo/16.03/ubuntu",
            "gpg-passphrase-path": "/etc/landscape/gpg-passphrase.txt",
            "gpg-home-path": "/etc/landscape/gpg"}
        self.hookenv.relations = {
            "hosted": {
                "hosted:1": {
                    "landscape-hosted/1": hosted_data,
                }
            }
        }
        relation = HostedRequirer({"config": {
            "root-url": "https://landscape.canonical.com/"}})
        self.assertEqual("https://archive.landscape.canonical.com/",
                         relation["hosted"][0]["archive-url"])
