from charmhelpers.core.services.helpers import RelationContext

from lib.hook import HookError

DEPLOYMENT_MODES = ("standalone", "edge", "staging", "production")


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
        "deployment-mode",  # Can be standalone/edge/staging/production.
    ]

    def get_data(self):
        super(HostedRequirer, self).get_data()
        if self.get(self.name) is None:
            # This means that we're not currently related to landscape-hosted,
            # so we set the deployment mode to standalone.
            self.update({self.name: [{"deployment-mode": "standalone"}]})
        else:
            # We're related to landscape-hosted, and it's safe to assume that
            # there's exactly one unit we're related to, since landscape-hosted
            # is a subordinate charm.
            [data] = self.get(self.name)
            deployment_mode = data["deployment-mode"]
            if deployment_mode not in DEPLOYMENT_MODES:
                raise HookError(
                    "Invalid deployment-mode '%s'" % deployment_mode)
