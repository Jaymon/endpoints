#!/usr/bin/env python

import sys
import os
import logging

try:
    from endpoints.interface.wsgi import Application
except ImportError:
    # this should only happen when running endpoints from source
    sys.path.append(os.path.realpath(os.path.join(os.path.dirname(__file__), "..", "..")))
    from endpoints.interface.wsgi import Application


if 'ENDPOINTS_PREFIX' not in os.environ:
    raise RuntimeError("ENDPOINTS_PREFIX environment variable not set")

# https://docs.python.org/2.7/library/logging.html#logging.basicConfig
logging.basicConfig(format="%(message)s", level=logging.DEBUG, stream=sys.stdout)
application = Application()

