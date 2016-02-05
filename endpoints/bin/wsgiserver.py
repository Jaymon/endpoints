#!/usr/bin/env python

import sys
import os
import argparse
import logging

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
    parser.add_argument('--prefix', "-P", help='The endpoints prefix')
    parser.add_argument('--host', "-H", help='The host to serve on in the form host:port')
    parser.add_argument('--count', "-C", help='How many requests to process until self termination', type=int, default=0)

    args = parser.parse_args()

    if not args.quiet:
        logging.basicConfig()

    os.environ["ENDPOINTS_HOST"] = args.host
    os.environ["ENDPOINTS_PREFIX"] = args.prefix

    s = Server()

    if args.count:
        s.serve_count(args.count)

    else:
        s.serve_forever()

    return 0


if __name__ == "__main__":
    sys.exit(console())

