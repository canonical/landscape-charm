import os
from fixtures import TempDir

from lib.relations.haproxy import ERRORFILES_MAP


class OfflineDir(TempDir):
    """Temporary offline dir populated with sample data."""

    rootdir = ""  # This is expected to be set

    def __init__(self, errorfiles_map=ERRORFILES_MAP):
        super(OfflineDir, self)
        self._errorfiles_map = errorfiles_map

    def setUp(self):
        super(OfflineDir, self).setUp()
        for filename in self._errorfiles_map.itervalues():
            fake_content = "Fake %s" % filename
            with open(os.path.join(self.path, filename), "w") as fd:
                fd.write(fake_content)
