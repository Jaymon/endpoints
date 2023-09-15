#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import argparse
import logging

from datatypes import ReflectName

from endpoints import __version__
from endpoints.config import environ


class EntryPoint(object):
    """Provides the CLI (command line interface) for running endpoints

    this is a class so subprojects can extend and manipulate how this works but
    take advantage of the foundation that lays and the subprojects can have
    basically similar interfaces to running on the command line
    """
    @classmethod
    def handle(cls):
        return cls()()

    def __init__(self):
        self.environ = environ
        self.parser = self.create_parser()

    def __call__(self):
        """cli hook

        :return: integer, the exit code
        """
        ret_code = 0

        args = self.parser.parse_args()

        # we want to make sure the directory can be imported from since chances
        # are the prefix module lives in that directory
        sys.path.append(args.directory)

        if not args.quiet:
            # https://docs.python.org/2.7/library/logging.html#logging.basicConfig
            logging.basicConfig(
                format="%(message)s",
                level=logging.DEBUG,
                stream=sys.stderr
            )

        logger = self.get_logger()

        self.environ.set_host(args.host)
        self.environ.set_controller_prefixes(args.prefix)

        if args.file:
            s = args.server_class(wsgifile=args.file)

        else:
            s = args.server_class()

        # we reset the host and update the environment because the server
        # could've set the port
        hostloc = ":".join(map(str, s.server_address))
        self.environ.set_host(hostloc)

        try:
            if args.count:
                logger.info("Listening on {} for {} requests".format(
                    hostloc,
                    args.count
                ))
                s.serve_count(args.count)

            else:
                logger.info("Listening on {}".format(hostloc))
                s.serve_forever()

        except KeyboardInterrupt:
            pass

        finally:
            logger.info("Server is shutting down")
            s.server_close()

        return ret_code

    def get_logger(self):
        return logging.getLogger(__name__)

    def create_parser(self):
        parser = argparse.ArgumentParser(
            description='Start an endpoints server',
            add_help=True,
            # https://stackoverflow.com/a/12151325/5006
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        parser.add_argument(
            "-v", "--version",
            action='version',
            version="%(prog)s {}".format(__version__)
        )
        parser.add_argument(
            "--quiet",
            action='store_true',
            dest='quiet'
        )
        parser.add_argument(
            '--prefix', "--controller-prefix", "-P",
            nargs="+",
            default=self.environ.get_controller_prefixes(),
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
            default=os.getcwd(),
            help='directory to run the server in, usually contains the prefix module path',
        )
        parser.add_argument(
            '--server', '-s',
            dest="server_class",
            default="endpoints.interface.wsgi:Server",
            type=self.get_server_class,
            help='The server interface endpoints will use',
        )

        return parser

    def get_server_class(self, classpath):
        """Returns the interface Server class

        :param modpath: the module path of the interface (eg,
            endpoints.interface.wsgi)
        :returns: Server class
        """
        classpath = ReflectName(classpath)
        s = classpath.get_class()
        if not s:
            raise ValueError(f"Could not resolve {classpath}")

        return s


if __name__ == "__main__":
    sys.exit(EntryPoint.handle())

