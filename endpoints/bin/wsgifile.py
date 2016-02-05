#!/usr/bin/env python

import os
import logging

from endpoints.interface.wsgi import Application


if 'ENDPOINTS_PREFIX' not in os.environ:
    raise RuntimeError("ENDPOINTS_PREFIX environment variable not set")

logging.basicConfig()
application = Application()

