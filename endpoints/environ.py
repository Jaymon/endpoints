# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os


def get(key, default=None, namespace="ENDPOINTS_"):
    if namespace and not key.startswith(namespace):
        key = namespace + key

    r = os.environ.get(key, default)
    return r


ENCODING = get("ENCODING", "UTF-8")
"""Default encoding"""

HOST = get("HOST", "localhost:8080")
"""The host string, usually just domain or domain:port, this is used by the server
classes and also the tests"""

