import subprocess

from charmhelpers.core import hookenv

def is_elected_leader(self):
    output = subprocess.check_output(["is-leader"])
    hookenv.log("is-leader: " + repr(output))
    return output.strip() == "True"
