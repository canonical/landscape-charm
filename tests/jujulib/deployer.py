from os import path
import tempfile
import shutil
import logging
import subprocess


class Deployer(object):

    def __init__(self):
        """Create a deployer Object"""
        pass
    
    def _stage_deployer_dir(self, deployer_dir):
        """
        Stage the directory for calling deployer.  Return the name
        of the created directory.
        """
        charm_src = path.dirname(path.dirname(__file__))
        charm_dest = path.join(deployer_dir, "precise", "landscape")
        shutil.copytree(charm_src, charm_dest)

    def deploy(self, target, config_files, timeout=None):
        """
        Run deployer.
        
        @param target: target to deployer in the config file.
        @param config_files: list of config files to pass to deployer (-c)
        """
        try:
            deployer_dir = tempfile.mkdtemp()
            self._stage_deployer_dir(deployer_dir)
            args = ["juju-deployer", "-vdWL"]
            for config_file in config_files:
                args.extend(["-c", config_file])
            args.append(target)
            if timeout is not None:
                args.extend(["timeout", timeout])
            logging.info("Calling Juju-deployer: %s" % args)
            subprocess.check_call(args, cwd=deployer_dir)
        finally:
            shutil.rmtree(self.deployer_dir)
