import json
import subprocess

def is_elected_leader(resource, subprocess=subprocess):
    output = subprocess.check_output(["is-leader", "--format", "json"])
    return json.loads(output)
