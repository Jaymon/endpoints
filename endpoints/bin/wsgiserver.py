#!/usr/bin/env python

import sys
import os
import argparse
import logging
import runpy

try:
    import endpoints
except ImportError:
    # this should only happen when running endpoints from source
    sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..")))
    import endpoints
from endpoints.interface.wsgi import Server


def console():
    '''
    cli hook
    return -- integer -- the exit code
    '''
    parser = argparse.ArgumentParser(description='Start an endpoints WSGI server', add_help=True)
    #parser.add_argument('--debug', dest='debug', action='store_true', help='print debugging info')
    parser.add_argument("-v", "--version", action='version', version="%(prog)s {}".format(endpoints.__version__))
    parser.add_argument("--quiet", action='store_true', dest='quiet')
    parser.add_argument('--prefix', "--controller-prefix", "-P", required=True, help='The endpoints prefix')
    parser.add_argument(
        '--file', "-F", "--wsgi-file", "--wsgifile",
        dest="file",
        default="",
        help='The wsgi file, the file that has an application callable'
    )
    parser.add_argument('--host', "-H", required=True, help='The host to serve on in the form host:port')
    parser.add_argument('--count', "-C", help='How many requests to process until self termination', type=int, default=0)
    parser.add_argument(
        '--dir', "-D", "--directory",
        dest="directory",
        default=os.getcwd(),
        help='directory to run the server in, usually contains the prefix module path',
    )

    args = parser.parse_args()

    # we want to make sure the directory can be imported from since chances are
    # the prefix module lives in that directory
    sys.path.append(args.directory)

    if not args.quiet:
        # https://docs.python.org/2.7/library/logging.html#logging.basicConfig
        logging.basicConfig(format="%(message)s", level=logging.DEBUG, stream=sys.stdout)

    logger = logging.getLogger(__name__)
    os.environ["ENDPOINTS_HOST"] = args.host
    os.environ["ENDPOINTS_PREFIX"] = args.prefix

    s = Server()

    if args.file:
        # get the application from the passed in wsgi file and use that to serve requests
        ret = runpy.run_path(args.file)
        s.application = ret["application"]

    if args.count:
        logger.info("Listening on {} for {} requests".format(args.host, args.prefix))
        s.serve_count(args.count)

    else:
        logger.info("Listening on {}".format(args.host))
        s.serve_forever()

    return 0


if __name__ == "__main__":
    sys.exit(console())

