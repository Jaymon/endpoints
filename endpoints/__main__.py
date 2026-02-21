#!/usr/bin/env python
# -*- coding: utf-8 -*-
import sys
import os
import argparse
import logging
from wsgiref.simple_server import make_server

from datatypes import ReflectName, logging, Host

from endpoints import __version__
from endpoints.config import environ


logger = logging.getLogger(__name__)


def application() -> int:
    """Provides the CLI (command line interface) for running endpoints in
    WSGI mode"""
    ret_code = 0

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
        #nargs="+",
        action="append",
        dest="prefixes",
        default=environ.get_controller_prefixes(),
        help='The controller prefix(es) (python modpaths where Controller subclasses are found)'
    )
    parser.add_argument(
        '--host', "-H",
        #default="localhost:3030",
        type=Host,
        default="localhost",
        help='The host to serve on in the form host:port'
    )
    parser.add_argument(
        '--dir', "-D", "--directory",
        dest="directory",
        default=os.getcwd(),
        help='directory to run the server in, usually contains the prefix module path',
    )
    parser.add_argument(
        "application",
        type=ReflectName,
        default="",
        help="The application path in the form module:Class.callable",
    )

    args = parser.parse_args()

    # we want to make sure the directory can be imported from since chances
    # are the prefix module lives in that directory
    sys.path.append(args.directory)

    if args.quiet:
        logging.quick_config(level="WARNING")

    else:
        logging.quick_config(level="DEBUG")

    if args.application:
        environ.set_controller_prefixes(args.prefixes)
        app = args.application.resolve()

    else:
        from endpoints.interface import Application
        app = Application(args.prefixes)

    environ.set_host(str(args.host))

    if args.prefixes:
        environ.set_controller_prefixes(args.prefixes)

    # https://docs.python.org/3/library/wsgiref.html#wsgiref.simple_server.make_server
    s = make_server(args.host[0], args.host[1], app)

    # we reset the host and update the environment because the server
    # could've set the port
    hostloc = ":".join(map(str, s.server_address))
    environ.set_host(hostloc)

    try:
        logger.info("Listening on {}".format(hostloc))
        s.serve_forever()

    except KeyboardInterrupt:
        pass

    except Exception:
        ret_code = 1

    finally:
        logger.info("Server is shutting down")
        #s.close()
        s.server_close()

    return ret_code


if __name__ == "__main__":
    sys.exit(application())

