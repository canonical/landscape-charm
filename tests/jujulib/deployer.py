from os import path
import tempfile
import shutil
import logging
import subprocess


class Deployer(object):
    """
    Simple wrapper around juju-deployer.  It's designed to copy the current
    charm branch in place in a staging directory where juju-deployer will be
    called.  Juju-deployer will then use that when references to "lp:<charm>"
    is used.
    """

    def _stage_deployer_dir(self, deployer_dir, series):
        """Stage the directory for calling deployer."""
        charm_src = path.dirname(path.dirname(path.dirname(__file__)))
        charm_dest = path.join(deployer_dir, series, "landscape")
        shutil.copytree(charm_src, charm_dest)

    def deploy(self, target, config_files, timeout=None, update_charms=False):
        """
        Use juju-deployer to install `target` on current `juju env`

        @param target: target to deploye in the config file.
        @param config_files: list of config files to pass to deployer (-c)
        @param timeout: timeout in seconds (int or string is OK)
        @param update_charms: update the charms before deploying (-u)
        """
        deployer_dir = None
        try:
            deployer_dir = tempfile.mkdtemp()
            for series in ["precise", "trusty"]:
                self._stage_deployer_dir(deployer_dir, series)
            args = ["juju-deployer", "-vdWL", "-w 180"]
            if update_charms:
                args.append("-u")
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
