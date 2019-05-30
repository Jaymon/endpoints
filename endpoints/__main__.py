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
from endpoints.interface.wsgi import Server
from endpoints import environ


def console():
    '''
    cli hook
    return -- integer -- the exit code
    '''
    parser = argparse.ArgumentParser(description='Start an endpoints WSGI server', add_help=True)
    #parser.add_argument('--debug', dest='debug', action='store_true', help='print debugging info')
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
        default=environ.get_controller_prefixes(),
        help='The endpoints controller prefix(es)'
    )
    parser.add_argument(
        '--file', "-F", "--wsgi-file", "--wsgifile",
        dest="file",
        default="",
        help='The wsgi file, the file that has an application callable'
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
#     parser.add_argument(
#         '--config', "--config-script", "-S",
#         dest="config_script",
#         default="",
#         help='This script will be loaded before Server is created allowing custom configuration',
#     )

    args = parser.parse_args()

    # we want to make sure the directory can be imported from since chances are
    # the prefix module lives in that directory
    sys.path.append(args.directory)

    if not args.quiet:
        # https://docs.python.org/2.7/library/logging.html#logging.basicConfig
        logging.basicConfig(format="%(message)s", level=logging.DEBUG, stream=sys.stdout)

    logger = logging.getLogger(__name__)
    os.environ["ENDPOINTS_HOST"] = args.host
    environ.HOST = args.host
    for i, prefix in enumerate(args.prefix, 1):
        os.environ["ENDPOINTS_PREFIX_{}".format(i)] = prefix
    #environ.PREFIXES = args.prefix

    config = {}
    if args.file:
        # load the configuration file
        config = runpy.run_path(args.file)

#     if args.config_script:
#         # load a config script so you can customize the environment
#         h = "wsgiserver_config_{}".format(uuid.uuid4())
#         config_module = imp.load_source(h, args.config_script)

    s = Server()

    if "application" in config:
        s.application = config["application"]

    if args.count:
        logger.info("Listening on {} for {} requests".format(s.hostloc, args.prefix))
        s.serve_count(args.count)

    else:
        logger.info("Listening on {}".format(s.hostloc))
        s.serve_forever()

    return 0


if __name__ == "__main__":
    try:
        sys.exit(console())
    except KeyboardInterrupt:
        sys.exit(0)

