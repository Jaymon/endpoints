# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import subprocess
import os
import sys
import re
import time
import logging
import threading
from collections import deque

from .. import environ
from ..compat.environ import *
from ..utils import String, ByteString, Path
from ..http import Url
from ..reflection import ReflectModule


logger = logging.getLogger(__name__)


class ServerThread(threading.Thread):
    """Used internally by the Client classes to start one of the server clients
    in a separate thread"""
    def __init__(self, server):
        super(ServerThread, self).__init__()
        self.server = server
        self.daemon = True
        self.logger = server.logger

    def flush(self, line):
        self.server.logger.info("{:0>5}: {}".format(self.server.process.pid, String(line)))
        #sys.stdout.write(String(line))
        #sys.stdout.flush()

    def run(self):
        process = self.server.process
        try:
            # Poll process for new output until finished
            for line in iter(process.stdout.readline, b""):
                line = String(line).rstrip()
                self.server.buf.append(line)
                if not self.server.quiet:
                    self.flush(line)

        except Exception as e:
            if not self.server.quiet:
                self.flush(e)
            raise

        finally:
            count = 0
            if process:
                try:
                    process.terminate()

                except OSError:
                    pass

                else:
                    while count < 50:
                        count += 1
                        time.sleep(0.1)
                        if process.poll() != None:
                            break

                    if process.poll() == None:
                        process.kill()

                finally:
                    # fixes ResourceWarning: unclosed file <_io.BufferedReader name=4>
                    # finally figured this out from captain, so I had evidently
                    # hunted it down before
                    process.stdout.close()


class WebServer(object):
    """This "client" is handy to get a simple testing server up and running

    it is mainly handy for testing purposes, we found that we were copy/pasting
    basically the same code to test random services and so it seemed like a good
    idea to move the base code into endpoints so all our projects could share it.

    :example:
        server = WebServer("foo.bar")
        server.start()
    """

    bufsize = 1000
    """how many lines to buffer of output, set to 0 to suppress all output"""

    quiet = False
    """this is the default quiet setting for running a script, if False output is printed to stdout"""

    host_regex = r"^Listening\s+on\s+(([^:]+):(\d+))$"
    """This regex is used to find the correct host from the output from the server in find_host"""

    @property
    def logger(self):
        logger = logging.getLogger("{}.WebServer".format(__name__))
        if len(logger.handlers) == 0:
            logger.setLevel(logging.INFO)
            log_handler = logging.StreamHandler(stream=sys.stdout)
            log_handler.setFormatter(logging.Formatter('%(message)s'))
            logger.addHandler(log_handler)
            logger.propagate = False
        return logger

    @property
    def environ(self):
        env = getattr(self, "_environ", None)
        if env: return env

        env = dict(os.environ)

        # pwd needed when running endpoints as a local module (eg, python -m endpoints)
        pwd = ReflectModule(__name__.split(".")[0]).path
        pythonpath = pwd + os.pathsep + self.cwd
        #pythonpath = self.cwd

        if "PYTHONPATH" in env:
            env["PYTHONPATH"] += os.pathsep + pythonpath
        else:
            env["PYTHONPATH"] = pythonpath

        for env_name in environ.get_prefix_names("ENDPOINTS_PREFIX"):
            env.pop(env_name)
        env["ENDPOINTS_PREFIX"] = self.controller_prefix

        return env

    @environ.setter
    def environ(self, v):
        self._environ = v

    @environ.deleter
    def environ(self):
        del self._environ

    @property
    def output(self):
        try:
            ret = "\n".join(self.buf)
        except AttributeError:
            ret = ""
        return ret

    def __init__(self, controller_prefix, host="", config_path="", **kwargs):
        """create a WSGI simple server

        controller_prefix -- string -- the endpoints prefix, the value that would be passed
            to ENDPOINTS_PREFIX
        host -- string -- the hostname:port, something like 127.0.0.1:8080 or 0.0.0.0:8080 or localhost
        :param config_path: a path to a .py file that contains configuration
        **kwargs -- dict -- provides an easy hook to set other instance properties
        """
        self.controller_prefix = controller_prefix
        if not host:
            host = environ.HOST
        self.host = Url(host).netloc if host else None

        self.cwd = Path(kwargs.get("cwd", os.getcwd()))
        self.config_path = config_path
        self.environ = kwargs.get("environ", kwargs.get("env", {}))
        self.process = None

    def kill(self):
        key = self.controller_prefix
        cmd = "pkill -9 -f \"{}\"".format(key)
        subprocess.call("{} > /dev/null 2>&1".format(cmd), shell=True)

    def get_start_cmd(self):
        cmd = [
            "python",
            "-m",
            __name__.split(".")[0],
            #"--host", self.host.netloc,
            "--prefix", self.controller_prefix,
            "--server", self.get_server_classpath(),
        ]

        if self.host:
            cmd.extend(["--host", self.host])

        config_path = self.config_path
        if config_path:
            cmd.extend(['--file', Path(config_path)])

        return cmd

    def get_server_classpath(self):
        raise NotImplementedError()

    def get_subprocess_args_and_kwargs(self):
        args = [self.get_start_cmd()]
        kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.cwd,
            env=self.environ
        )
        return args, kwargs

    def start(self, **kwargs):
        #import pdb; pdb.set_trace()
        args, kwargs = self.get_subprocess_args_and_kwargs()
        self.process = subprocess.Popen(*args, **kwargs)

        self.quiet = kwargs.pop("quiet", type(self).quiet)
        self.buf = deque(maxlen=self.bufsize)

        self.thread = ServerThread(self)
        self.thread.start()

        self.host = Url(self.find_host()).client_netloc

    def find_host(self):
        host = ""
        i = 0
        while not host:
            try:
                m = re.search(self.host_regex, self.buf[i], flags=re.I)
                if m:
                    host = m.group(1)
                else:
                    i += 1

            except IndexError:
                pass

        return host


    def stop(self):
        process = None
        try:
            process = self.process
            process.kill()

        except AttributeError:
            pass

        finally:
            self.kill()

            if process:
                process.stdout.close()

