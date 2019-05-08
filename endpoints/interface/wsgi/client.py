# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import threading
import os
import inspect
import subprocess
import time
import sys
from collections import deque

from ...compat.environ import *
from ...utils import Path, String
from ...http import Url
from ... import environ
from ...reflection import ReflectModule


class WSGIThread(threading.Thread):
    """Used internally by the Client classes to start one of the server clients
    in a separate thread"""
    def __init__(self, server):
        super(WSGIThread, self).__init__()
        self.server = server
        self._stop = threading.Event()
        self.daemon = True

    def stop(self):
        self._stop.set()

    def stopped(self):
        return self._stop.isSet()

    def flush(self, line):
        sys.stdout.write(String(line))
        sys.stdout.flush()

    def run(self):
        process = self.server.process
        try:
            # Poll process for new output until finished
            for line in iter(process.stdout.readline, ""):
                self.server.buf.append(line.rstrip())
                if not self.server.quiet:
                    self.flush(line)

                if self.stopped():
                    break

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


class WSGIServer(object):
    """This "client" is handy to get a simple wsgi server up and running

    it is mainly handy for testing purposes, we found that we were copy/pasting
    basically the same code to test random services and so it seemed like a good
    idea to move the base code into endpoints so all our projects could share it.

    example --

        server = WSGIServer("foo.bar")
        server.start()
    """

    #bin_script = "wsgiserver.py"

    bufsize = 1000
    """how many lines to buffer of output, set to 0 to suppress all output"""

    quiet = False
    """this is the default quiet setting for running a script, if False output is printed to stdout"""

    @property
    def environ(self):
        env = getattr(self, "_environ", None)
        if env: return env

        env = dict(os.environ)

        pwd = ReflectModule(__name__).path
        pythonpath = pwd + os.pathsep + self.cwd

        if "PYTHONPATH" in env:
            env["PYTHONPATH"] += os.pathsep + pythonpath
        else:
            env["PYTHONPATH"] = pythonpath

        if "ENDPOINTS_PREFIX" in env:
            if env["ENDPOINTS_PREFIX"] != self.controller_prefix:
                raise ValueError("ENDPOINTS_PREFIX ({}) and controller_prefix ({}) do not match".format(
                    env["ENDPOINTS_PREFIX"],
                    self.controller_prefix
                ))

        else:
            env["ENDPOINTS_PREFIX"] = self.controller_prefix

        return env

    @environ.setter
    def environ(self, v):
        self._environ = v

    @environ.deleter
    def environ(self):
        del self._environ

#     @property
#     def path(self):
#         return os.path.join(find_module_path(), "bin", self.bin_script)

    @property
    def output(self):
        try:
            ret = "\n".join(self.buf)
        except AttributeError:
            ret = ""
        return ret

    def __init__(self, controller_prefix, host="", wsgifile="", **kwargs):
        """create a WSGI simple server

        controller_prefix -- string -- the endpoints prefix, the value that would be passed
            to ENDPOINTS_PREFIX
        host -- string -- the hostname:port, something like 127.0.0.1:8080 or 0.0.0.0:8080 or localhost
        wsgifile -- string -- the path to the wsgi file that has an application callable
        **kwargs -- dict -- provides an easy hook to set other instance properties
        """
        self.controller_prefix = controller_prefix
        if not host:
            host = environ.HOST
        self.host = Url(host)

        self.cwd = Path(kwargs.get("cwd", os.curdir))
        self.wsgifile = wsgifile
        self.environ = kwargs.get("environ", kwargs.get("env", {}))
        self.process = None

    def kill(self):
        key = self.wsgifile
        if not key:
            key = self.host.netloc
        cmd = "pkill -9 -f \"{}\"".format(key)
        subprocess.call("{} > /dev/null 2>&1".format(cmd), shell=True)

    def get_start_cmd(self):
        cmd = [
            "python",
            "-m",
            __name__.split(".")[0],
            #"endpoints",
            #self.path,
            #"--host={}".format(self.host.netloc),
            "--host", self.host.netloc,
            #"--prefix={}".format(self.controller_prefix),
            "--prefix", self.controller_prefix,
        ]

        wsgifile = self.wsgifile
        if wsgifile:
            cmd.extend(['--file', Path(wsgifile)])

        return cmd

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

        self.thread = WSGIThread(self)
        self.thread.start()

        # if the buffer doesn't increase for 3 iterations then we assume the server
        # is fully started up, after 5 second we assume it's ready no matter what
        count = 0
        size = 0
        for x in range(50):
            time.sleep(0.1)
            if len(self.buf) > size:
                count = 0
                size = len(self.buf)
            else:
                count += 1
                if count > 3:
                    break

    def stop(self):
        """http://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread-in-python"""
        try:
            self.thread.stop()
        except AttributeError:
            pass

        self.kill()

