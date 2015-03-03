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

    def _create_local_yaml(self, tmpdir, config_files):
        """
        Create a local yaml file to adjust settings in the bundle.  Return the
        created file name to the caller.

        @param tmpdir: directory where we can write a yaml file.
        @param config_files: config file names are used to determine what
            bundles will be available for deployment.  This is important
            since overrides are deployer target specific. We have to know
            what targets are available, in order to override them.

        Respects and accounts for these files:
        - config/repo-file
        - config/license-file
        """
        # Will be appended to end of 'config_files' list.  This will in turn
        # be specified last on the juju-deployer command line, and will be able
        # to overwrite charm settings.  For instance we can use it to add a
        # custom license-file to the deployment.
        local_yaml_file = path.join(tmpdir, "99-local.yaml")
        local_yaml = {}

        # overridden options in landscape-charm, with the filename in the
        # config dir that we read.
        override_options = {"repository": "repo-file",
                            "license-file": "license-file"}

        # Base data structure for the landscape-charm that we will fill out
        # with options.
        landscape_service = {"charm": "landscape",
                             "branch": "lp:landscape-charm"}
        options = {}
        for option, filename in override_options.items():
            filepath = path.join(CHARM_SRC, "config", filename)
            if path.exists(filepath):
                options[option] = "include-file://%s" % filepath

        # Can't include a blank options section, deployer will choke
        if options:
            landscape_service["options"] = options

        for config in config_files:
            # target name == filename in our bundles branches.
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
            # Stage deployer directory for all supported series, even though
            # typically in a deploy attempt only one series is used.  Since
            # it's determined by a bundle, we have to be ready for whatever.
            for series in ["precise", "trusty"]:
                self._stage_deployer_dir(deployer_dir, series)
            config_files.append(
                self._create_local_yaml(deployer_dir, config_files))
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
