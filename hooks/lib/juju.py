"""
Simple python library for juju commands in the context of an
executing hook. Mostly wrappers around shell commands.
"""
import json
import os
import subprocess


class Juju(object):

    # XXX let's look at pulling in charmhelpers lib into Landscape soon
    def local_unit(self):
        """Local unit ID"""
        return os.environ["JUJU_UNIT_NAME"]

    def relation_set(self, *args, **kwargs):
        """
        Simple wrapper around relation-set, all arguments passed through.
        kwargs are also supported. C{args} are provided in case the key
        cannot be represented as a python variable.

        @param relation_id relation id to use (needed if not called in
            context of relation). Will be stripped from kwargs if present.
            if you need to set this, use an arg style argument "k=v"
        """
        cmd = ["relation-set"]
        if "relation_id" in kwargs:
            cmd.extend(["-r", kwargs["relation_id"]])
            del kwargs["relation_id"]
        cmd.extend("%s=%s" % (key, val) for key, val in kwargs.iteritems())
        cmd.extend(args)
        subprocess.call(cmd)

    def relation_ids(self, relation_name=None):
        """
        Wrapper around relation-ids Juju command. Output will be returned
        from parsed JSON, which in the case of this command is a list of
        strings.
        """
        args = ["relation-ids", "--format=json"]
        if relation_name is not None:
            args.append(relation_name)
        return json.loads(subprocess.check_output(args))

    def relation_list(self):
        """
        Wrapper around relation-list Juju command. Output will be returned
        from parsed JSON, which in the case of this command is a list of
        strings.
        """
        args = ["relation-list", "--format=json"]
        return json.loads(subprocess.check_output(args))

    def unit_get(self, *args):
        """Simple wrapper around unit-get, all arguments passed untouched"""
        get_args = ["unit-get"]
        get_args.extend(args)
        return subprocess.check_output(get_args).rstrip()

    def juju_log(self, *args, **kwargs):
        """
        Simple wrapper around juju-log, args are passed untouched.

        @param level CRITICAL | DEBUG | INFO | WARNING | ERROR
        """
        log_args = ["juju-log"]
        if "level" in kwargs:
            log_args.extend(["--log-level", kwargs["level"]])
        log_args.extend(args)
        subprocess.call(log_args)

    def config_get(self, scope=None):
        """
        Returns a dictionary containing all of the config information
        Optional parameter: scope
        scope: limits the scope of the returned configuration to the
        desired config item.
        """
        try:
            config_cmd_line = ["config-get"]
            if scope is not None:
                config_cmd_line.append(scope)
            config_cmd_line.append("--format=json")
            config_data = json.loads(subprocess.check_output(config_cmd_line))
        except Exception, e:
            subprocess.call(["juju-log", str(e)])
            config_data = None
        finally:
            return(config_data)

    def relation_get(self, scope=None, unit_name=None, relation_id=None):
        """
        Returns a dictionary containing the relation information
        @param scope: limits the scope of the returned data to the
                    desired item.
        @param unit_name: limits the data ( and optionally the scope )
                        to the specified unit
        @param relation_id: specify relation id for out of context usage.
        """
        try:
            relation_cmd_line = ["relation-get", "--format=json"]
            if relation_id is not None:
                relation_cmd_line.extend(("-r", relation_id))
            if scope is not None:
                relation_cmd_line.append(scope)
            else:
                relation_cmd_line.append("")
            if unit_name is not None:
                relation_cmd_line.append(unit_name)
            relation_data = json.loads(
                subprocess.check_output(relation_cmd_line))
        except Exception, e:
            subprocess.call(["juju-log", str(e)])
            relation_data = None
        finally:
            return(relation_data)
