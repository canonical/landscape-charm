import json
import subprocess

def is_elected_leader(resource, is_leader_exec="is-leader"):
    output = subprocess.check_output([is_leader_exec, "--format", "json"])
    return json.loads(output)
