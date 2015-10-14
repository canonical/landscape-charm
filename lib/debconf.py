import os
import subprocess

from lib.paths import DPKG_RECONFIGURE, DEBCONF_SET_SELECTIONS

OPTION_TEMPLATE = "%(package)s %(package)s/%(name)s %(kind)s %(value)s\n"


class DebConf(object):
    """Simple facade around for configuring a package via debconf."""

    def __init__(self, package, schema, subprocess=subprocess):
        """
        @param package: The package to configure.
        @param schema: A dict mapping available option names to the type
            of their values.
        @param subprocess: The subprocess module to use (for unit tests).
        """
        self._package = package
        self._schema = schema
        self._subprocess = subprocess

    def set(self, options):
        """Set the the values of the given options.

        @param options: A dict mapping option names to the desired values.
        """
        text = ""
        for name, value in sorted(options.items()):
            text += self._format_option(name, value)
        process = self._subprocess.Popen(
            [DEBCONF_SET_SELECTIONS], stdin=subprocess.PIPE)
        process.communicate(text)

    def reconfigure(self):
        """Reconfigure the package in non-interactive mode."""
        env = os.environ.copy()

        # XXX It seems that some packages (e.g. postfix) are not happy with
        #     the 'noninteractive' frontend, and don't really reconfigure
        #     anything in that case. Using the editor frontend and pointing
        #     the editor to a no-op like /bin/true workarounds the problem.
        env["EDITOR"] = "/bin/true"

        # XXX Set the frontend using the environment variable and not the -f
        #     command line options, since dpkg-reconfigure prefers the former
        #     over the latter, and juju sets it to noninteractive by default.
        env["DEBIAN_FRONTEND"] = "editor"

        self._subprocess.check_call([DPKG_RECONFIGURE, self._package], env=env)

    def _format_option(self, name, value):
        """Format an option line to feed to debconf-set-selections."""
        kind = self._schema.get(name)
        if not kind:
            raise RuntimeError("Unknown option '%s'" % name)
        return OPTION_TEMPLATE % dict(
            package=self._package, name=name, kind=kind, value=value)
