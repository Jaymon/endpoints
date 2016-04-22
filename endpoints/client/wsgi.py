import threading
import os
import inspect
import endpoints
import subprocess
import time
import sys


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

            # flush any remaining output
#             line = process.stdout.read()
#             self.flush(line)

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

        server = WSGIClient("foo.bar")
        server.start()
    """

    script = "wsgiserver.py"

    @property
    def path(self):
        path = self._path
        if not path:
            path = self.autodiscover_path()
        return path

    def __init__(self, controller_prefix, path="", port=8080, host="0.0.0.0", quiet=False):
        """create a WSGI simple server

        controller_prefix -- string -- the endpoints prefix, the value that would be passed
            to ENDPOINTS_PREFIX
        path -- string -- the path to the wsgi file, this will be set to self.autodiscover_path()
            if it isn't passed in
        port -- integer -- the port to use
        host -- string -- the host, something like 127.0.0.1 or 0.0.0.0 or localhost
        quiet -- boolean -- True to silence server output, False (default) to print output to stdout
        """
        self.cwd = os.curdir
        self.controller_prefix = controller_prefix
        self._path = path
        self.host = host
        self.port = port
        self.quiet = quiet
        self.env = {}

    def kill(self):
        cmd = "pkill -9 -f {}".format(self.path)
        subprocess.call("{} > /dev/null 2>&1".format(cmd), shell=True)

    def autodiscover_path(self):
        # get this source directory
        endpoints_dir = os.path.dirname(inspect.getsourcefile(endpoints))
        #this_dir = os.path.dirname(inspect.getsourcefile(WSGIClient))

        # now get the endpoints
        #os.path.join(, "..")
        return os.path.join(endpoints_dir, "bin", self.script)

    def get_start_cmd(self):
        return [
            "python",
            self.path,
            "--host={}:{}".format(self.host, self.port),
            "--prefix={}".format(self.controller_prefix),
        ]

    def get_subprocess_args_and_kwargs(self):
        args = [self.get_start_cmd()]
        kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=self.cwd,
        )

        env = dict(os.environ)
        env.update(self.env)
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
        self.thread.stop()
        self.kill()


class UWSGIServer(WSGIServer):

    script = "wsgifile.py"

    def get_start_cmd(self):
        return [
            "uwsgi",
            "--http={}:{}".format(self.host, self.port),
            "--show-config",
            "--master",
            "--processes=1",
            "--cpu-affinity=1",
            "--thunder-lock",
            "--http-raw-body",
            "--chdir={}".format(self.cwd),
            "--wsgi-file={}".format(self.path),
        ]

    def get_subprocess_args_and_kwargs(self):
        self.env["ENDPOINTS_PREFIX"] = self.controller_prefix
        return super(UWSGIServer, self).get_subprocess_args_and_kwargs()

