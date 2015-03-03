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
        Create a local yaml file to adjust settings in the bundle.  Return the
        created file name to the caller.

        @param deployer_dir: directory where we have staged the charms.
        @param series: ubuntu series being used.
        @param config_files: config file names are used to determine what
                             bundles will be available for deployment.

        Respects and accounts for these files:
        - config/repo-file
        - config/license-file
        """
        landscape_dir = path.join(deployer_dir, series, "landscape")
        # Will be appened to end of 'config_files' list.  This will in turn
        # be specified last on the juju-deployer command line, and will be able
        # to overwrite charm settings.  For instance we can use it to add a
        # custom license-file to the deployment.
        local_yaml_file = path.join(landscape_dir, "config", "99-local.yaml")
        local_yaml = {}
        landscape_service = {
            "charm": "landscape",
            "branch": "lp:landscape-charm"}
        options = {}
        if path.exists(path.join(CHARM_SRC, "config", "repo-file")):
            options["repository"] = "include-file://repo-file"
        if path.exists(path.join(CHARM_SRC, "config", "license-file")):
            options["license-file"] = "include-file://license-file"
        # Can't include a blank options section, deployer will choke
        if options:
            landscape_service["options"] = options

        for config in config_files:
            # as per bundle spec, target name == filename
            target = path.basename(config).rstrip(".yaml")
            local_yaml[target] = {"services": {}}
            for service in ["landscape-msg", "landscape"]:
                local_yaml[target]["services"][service] = landscape_service

        with open(local_yaml_file, "w") as f:
            f.write(yaml.dump(local_yaml, default_flow_style=False))
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
