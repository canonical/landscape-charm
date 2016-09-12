from charmhelpers.core.services.helpers import RelationContext

from lib.error import CharmError

DEPLOYMENT_MODES = ("standalone", "edge", "staging", "production")


class InvalidDeploymentModeError(CharmError):
    """Invalid deployment mode."""

    def __init__(self, deployment_mode):
        message = "Invalid deployment-mode '%s'" % deployment_mode
        super(InvalidDeploymentModeError, self).__init__(message)


class DuplicateArchiveNameError(CharmError):
    """Same archive name was used at least twice in a hosted relation data."""

    def __init__(self, deployment_mode):
        message = "Duplicate archive name '%s' used twice in proxy-ppas." % (
            deployment_mode)
        super(DuplicateArchiveNameError, self).__init__(message)


class MissingSupportedReleaseUrlError(CharmError):
    """PPA was provided in supported-releases, but is not defined at all."""

    def __init__(self, release_name):
        message = (
            "PPA '%s' listed in supported-releases does not have "
            "the URL defined in ppas-to-proxy." % (release_name))
        super(MissingSupportedReleaseUrlError, self).__init__(message)


class HostedRequirer(RelationContext):
    """Relation data requirer for the 'hosted' interface.

    This relation acquires information from the landscape-hosted subordinate,
    which will affect local configuration (for instance 'deployment-mode').

    If we're not related to any landscape-hosted subordinate, then this data
    manager will simply fall back to stock data setting a 'standalone' mode.
    """
    name = "hosted"
    interface = "landscape-hosted"
    required_keys = [
        "deployment-mode",     # Can be standalone/edge/staging/production.
        "supported-releases",  # A comma-separated list of release short names.
        "ppas-to-proxy",       # A map of release names to archive URLs in the
                               # name1=url1,name2=url2 format.
    ]

    def get_data(self):
        super(HostedRequirer, self).get_data()
        data = self.get(self.name)
        if data is None:
            # This means that we're not currently related to landscape-hosted,
            # so we set the deployment mode to standalone.
            self.update({self.name: [{"deployment-mode": "standalone"}]})
        elif len(data) > 0:
            # We're related to landscape-hosted, and it's safe to assume that
            # there's exactly one unit we're related to, since landscape-hosted
            # is a subordinate charm.
            deployment_mode = data[0]["deployment-mode"]
            if deployment_mode not in DEPLOYMENT_MODES:
                raise InvalidDeploymentModeError(deployment_mode)

            ppas_to_proxy = data[0].get("ppas-to-proxy")
            archives = {}
            if ppas_to_proxy:
                for archive in ppas_to_proxy.split(","):
                    archive_name, archive_url = archive.split("=", 1)
                    if archive_name.strip() not in archives:
                        archives[archive_name.strip()] = archive_url.strip()
                    else:
                        raise DuplicateArchiveNameError(archive_name.strip())
                data[0].update({"ppas-to-proxy": archives})

            supported_releases = data[0].get("supported-releases")
            if supported_releases:
                releases = []
                for release in supported_releases.split(","):
                    release = release.strip()
                    if release not in ppas_to_proxy:
                        raise MissingSupportedReleaseUrlError(release)
                    releases.append(release)
                data[0].update({"supported-releases": releases})
