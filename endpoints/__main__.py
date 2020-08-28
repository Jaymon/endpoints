#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import sys
import os
import argparse
import logging
import runpy
import uuid

from endpoints import __version__
#from endpoints.interface.wsgi import Server
from endpoints import environ
from endpoints.reflection import ReflectModule


class Console(object):
    """Provides the CLI (command line interface) for running endpoints

    this is a class so subprojects can extend and manipulate how this works but
    take advantage of the foundation that lays and the subprojects can have basically
    similar interfaces to running on the command line
    """
    def __init__(self):
        self.environ = environ
        self.parser = self.create_parser()

    def __call__(self):
        """cli hook
        :return: integer, the exit code
        """
        ret_code = 0

        args = self.parse_args()

        # we want to make sure the directory can be imported from since chances are
        # the prefix module lives in that directory
        sys.path.append(args.directory)

        if not args.quiet:
            # https://docs.python.org/2.7/library/logging.html#logging.basicConfig
            logging.basicConfig(format="%(message)s", level=logging.DEBUG, stream=sys.stderr)
            #logging.basicConfig(format='[%(levelname).1s|%(asctime)s|%(filename)s:%(lineno)s] %(message)s', level=logging.DEBUG, stream=sys.stderr)

        logger = self.get_logger()

        self.environ.set_host(args.host)
        self.environ.set_controller_prefixes(args.prefix)

        config = {}
        if args.file:
            # load the configuration file
            config = runpy.run_path(args.file)


    #     if args.config_script:
    #         # load a config script so you can customize the environment
    #         h = "wsgiserver_config_{}".format(uuid.uuid4())
    #         config_module = imp.load_source(h, args.config_script)

        s = args.server()
        self.environ.set_host(s.hostloc)

        if "application" in config:
            s.application = config["application"]

        try:
            if args.count:
                logger.info("Listening on {} for {} requests".format(s.hostloc, args.count))
                s.serve_count(args.count)

            else:
                logger.info("Listening on {}".format(s.hostloc))
                s.serve_forever()

        except KeyboardInterrupt:
            pass

        return ret_code

    def get_logger(self):
        return logging.getLogger(__name__)

    def get_version(self):
        return __version__

    def get_default_controller_prefixes(self):
        return self.environ.get_controller_prefixes()

    def parse_args(self):
        return self.parser.parse_args()

    def get_default_directory(self):
        return os.getcwd()

    def create_parser(self):
        parser = argparse.ArgumentParser(
            description='Start an endpoints WSGI server',
            add_help=True,
            # https://stackoverflow.com/a/12151325/5006
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        parser.add_argument(
            "-v", "--version",
            action='version',
            version="%(prog)s {}".format(self.get_version())
        )
        parser.add_argument(
            "--quiet",
            action='store_true',
            dest='quiet'
        )
        parser.add_argument(
            '--prefix', "--controller-prefix", "-P",
            nargs="+",
            default=self.get_default_controller_prefixes(),
            help='The controller prefix(es) (python modpaths where Controller subclasses are found)'
        )
        parser.add_argument(
            '--file', "-F", "--config", "--wsgi-file", "--wsgifile",
            dest="file",
            default="",
            help='A config file, a .py file containing configuration to run before starting the server'
        )
        parser.add_argument(
            '--host', "-H",
            #default="localhost:3030",
            default="localhost",
            help='The host to serve on in the form host:port'
        )
        parser.add_argument(
            '--count', "-C",
            help='How many requests to process until self termination',
            type=int,
            default=0
        )
        parser.add_argument(
            '--dir', "-D", "--directory",
            dest="directory",
            default=self.get_default_directory(),
            help='directory to run the server in, usually contains the prefix module path',
        )
        parser.add_argument(
            '--server', '-s',
            dest="server",
            default=self.get_default_server(),
            type=self.get_server,
            help='The server interface endpoints will use',
        )

        return parser

    def get_default_server(self):
        return "endpoints.interface.wsgi.Server"

    def get_server(self, classpath):
        """Returns the interface Server class

        :param modpath: the module path of the interface (eg, endpoints.interface.wsgi)
        :returns: Server class
        """
        parts = classpath.rsplit(".", 1)
        modpath = parts[0]
        classname = parts[1] if len(parts) > 1 else "Server"

        try:
            rm = ReflectModule(modpath)
            s = getattr(rm.module, classname)

        except (ImportError, AttributeError):
            rm = ReflectModule("endpoints.interface.{}".format(modpath))
            s = getattr(rm.module, classname)

        return s


console = Console()


if __name__ == "__main__":
    sys.exit(console())

