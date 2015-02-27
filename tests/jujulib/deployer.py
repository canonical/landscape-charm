import logging
from os import path
import shutil
import subprocess
import tempfile
import yaml

CHARM_SRC = path.dirname(path.dirname(path.dirname(__file__)))

class Deployer(object):
    """
    Simple wrapper around juju-deployer.  It's designed to copy the current
    charm branch in place in a staging directory where juju-deployer will be
    called.  Juju-deployer will then use that when references to "lp:<charm>"
    is used.
    """

    def _stage_deployer_dir(self, deployer_dir, series):
        """Stage the directory for calling deployer."""
        charm_dest = path.join(deployer_dir, series, "landscape")
        shutil.copytree(CHARM_SRC, charm_dest)

    def _create_local_yaml(self, deployer_dir, series, config_files):
        """
        Create a local yaml file to adjust settings in the deployed charm.
        Return the created file name to the caller.
        
        Respects:
        - config/repo-file
        - config/license-file
        - lp:landscape
        """
        landscape_dir = path.join(deployer_dir, series, "landscape")
        local_yaml = {}
        options = {}
        if path.exists(path.join(CHARM_SRC, "config", "repo-file")):
            options["repository"] = "include-file://repo-file"
        if path.exists(path.join(CHARM_SRC, "config", "license-file")):
            options["license-file"] = "include-file://license-file"

        for config in config_files:
            target = path.basename(config).rstrip(".yaml")
            for service in ["landscape-msg", "landscape"]:
                local_yaml[target] = {service: {
                    "charm": "",
                    "branch": "lp:landscape-charm"}}
                if options:
                    local_yaml[target][service]["options"] = options
        local_yaml_file = path.join(landscape_dir, "config", "local.yaml")
        with open(local_yaml_file, "w") as outfile:
            outfile.write(yaml.dump(local_yaml))
        return local_yaml_file

    def deploy(self, target, config_files, timeout=None):
        """
        Use juju-deployer to install `target` on current `juju env`

        @param target: target to deploye in the config file.
        @param config_files: list of config files to pass to deployer (-c)
        @param timeout: timeout in seconds (int or string is OK)
        """
        deployer_dir = None
        try:
            deployer_dir = tempfile.mkdtemp()
            for series in ["precise", "trusty"]:
                self._stage_deployer_dir(deployer_dir, series)
            config_files.append(self._create_local_yaml(
                deployer_dir, series, config_files))
            args = ["juju-deployer", "-vdWL", "-w 180"]
            for config_file in config_files:
                args.extend(["-c", config_file])
            args.append(target)
            if timeout is not None:
                args.extend(["--timeout", str(timeout)])
            logging.info("(cwd=%s) RUN: %s" % (deployer_dir, args))
            subprocess.check_call(args, cwd=deployer_dir)
        finally:
            if deployer_dir is not None:
                shutil.rmtree(deployer_dir)
