import json
import subprocess


def is_elected_leader(resource, subprocess=subprocess):
    """Return whether the current unit is the elected leader.

    It uses Juju's is-leader command, which guarantees leadership for at
    least 30 seconds.
    """
    output = subprocess.check_output(["is-leader", "--format", "json"])
    return json.loads(output)
