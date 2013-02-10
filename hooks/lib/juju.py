"""
Simple python library for juju commands in the context of an
executing hook.  Mostly wrappers around shell commands.
"""

import json
import subprocess

class Juju(object):

    def relation_set(self, *args, **kwargs):
        """
        Simple wrapper around relation-set, all arguments passed through.
        kwargs are also supported.  args are provided in case the key
        cannot be represented as a python variable.
        """
        set_args = ["relation-set"]
        for k,v in kwargs.iteritems():
            set_args.append("%s=%s" % (k, v))
        set_args.extend(args)
        subprocess.call(set_args)

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
            config_cmd_line = ['config-get']
            if scope is not None:
                config_cmd_line.append(scope)
            config_cmd_line.append('--format=json')
            config_data = json.loads(subprocess.check_output(config_cmd_line))
        except Exception, e:
            subprocess.call(['juju-log', str(e)])
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
            relation_cmd_line = ['relation-get', '--format=json']
            if relation_id is not None:
                relation_cmd_line.extend(('-r', relation_id))
            if scope is not None:
                relation_cmd_line.append(scope)
            else:
                relation_cmd_line.append('')
            if unit_name is not None:
                relation_cmd_line.append(unit_name)
            relation_data = json.loads(subprocess.check_output(relation_cmd_line))
        except Exception, e:
            subprocess.call(['juju-log', str(e)])
            relation_data = None
        finally:
            return(relation_data)
