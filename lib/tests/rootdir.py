import os

from fixtures import TempDir

from lib.relations.haproxy import ERRORFILES_MAP
from lib.paths import Paths


class RootDir(TempDir):
    """Filesystem tree that mimics are a root filesystem.

    This fixtures creates a filesystem tree that has the same layout of
    what the charm expects to find, but it's rooted at a temporary directory.
    """

    def setUp(self):
        super(RootDir, self).setUp()
        self.paths = Paths(self.path)
        os.makedirs(self.paths.config_dir())
        os.makedirs(os.path.dirname(self.paths.ssl_certificate()))
        os.makedirs(self.paths.offline_dir())
        for path in ERRORFILES_MAP.itervalues():
            with open(os.path.join(self.paths.offline_dir(), path), "w") as fd:
                fd.write("Fake %s" % path)
