import threading
import os
import inspect
import subprocess
import time
import sys

import endpoints
from ..utils import Host, Path


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
        sys.stdout.write(line)
        sys.stdout.flush()

    def run(self):
        process = None
        try:
            args, kwargs = self.server.get_subprocess_args_and_kwargs()
            process = subprocess.Popen(*args, **kwargs)

            # Poll process for new output until finished
            for line in iter(process.stdout.readline, ""):
                if not self.server.quiet:
                    self.flush(line)

                if self.stopped():
                    break

        except Exception as e:
            if not self.server.quiet:
                print e
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


class WSGIServer(object):
    """This "client" is handy to get a simple wsgi server up and running

    it is mainly handy for testing purposes, we found that we were copy/pasting
    basically the same code to test random services and so it seemed like a good
    idea to move the base code into endpoints so all our projects could share it.

    example --

        server = WSGIServer("foo.bar")
        server.start()
    """

    bin_script = "wsgiserver.py"

    @property
    def path(self):
        endpoints_dir = os.path.dirname(inspect.getsourcefile(endpoints))
        return os.path.join(endpoints_dir, "bin", self.bin_script)

    def __init__(self, controller_prefix, host="localhost:8080", wsgifile="", quiet=False, **kwargs):
        """create a WSGI simple server

        controller_prefix -- string -- the endpoints prefix, the value that would be passed
            to ENDPOINTS_PREFIX
        host -- string -- the hostname:port, something like 127.0.0.1:8080 or 0.0.0.0:8080 or localhost
        wsgifile -- string -- the path to the wsgi file that has an application callable
        quiet -- boolean -- True to silence server output, False (default) to print output to stdout
        **kwargs -- dict -- provides an easy hook to set other instance properties
        """
        self.controller_prefix = controller_prefix
        self.host = Host(host)
        self.quiet = quiet

        self.cwd = Path(kwargs.get("cwd", os.curdir))
        self.wsgifile = wsgifile
        self.env = kwargs.get("env", {})

    def kill(self):
        key = self.wsgifile
        if not key:
            key = self.path
        cmd = "pkill -9 -f {}".format(key)
        subprocess.call("{} > /dev/null 2>&1".format(cmd), shell=True)

    def get_start_cmd(self):
        cmd = [
            "python",
            self.path,
            "--host={}".format(self.host),
            "--prefix={}".format(self.controller_prefix),
        ]

        wsgifile = self.wsgifile
        if wsgifile:
            cmd.append('--file={}'.format(Path(wsgifile)))

        return cmd

    def get_subprocess_args_and_kwargs(self):
        args = [self.get_start_cmd()]
        kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.cwd,
        )

        env = dict(os.environ)
        env.update(self.env)

        if "PYTHONPATH" in env:
            env["PYTHONPATH"] += os.pathsep + self.cwd
        else:
            env["PYTHONPATH"] = self.cwd

        kwargs["env"] = env

        return args, kwargs

    def start(self):
        self.thread = WSGIThread(self)
        self.thread.start()
        # we give it some time to fully start up before returning control, I would
        # love a better way to do this but I can't think of anything
        time.sleep(1) 

    def stop(self):
        """http://stackoverflow.com/questions/323972/is-there-any-way-to-kill-a-thread-in-python"""
        try:
            self.thread.stop()
        except AttributeError:
            pass

        self.kill()


class UWSGIServer(WSGIServer):

    bin_script = "wsgifile.py"
    process_count = 1

    def __init__(self, *args, **kwargs):
        super(UWSGIServer, self).__init__(*args, **kwargs)

        if not self.wsgifile:
            self.wsgifile = self.path

    def get_start_cmd(self):
        return [
            "uwsgi",
            "--http={}".format(self.host),
            "--show-config",
            "--master",
            "--processes={}".format(self.process_count),
            "--cpu-affinity=1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir={}".format(self.cwd),
            "--wsgi-file={}".format(Path(self.wsgifile)),
        ]

    def get_subprocess_args_and_kwargs(self):
        self.env["ENDPOINTS_PREFIX"] = self.controller_prefix
        return super(UWSGIServer, self).get_subprocess_args_and_kwargs()

