# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import os


def get(key, default=None, namespace="ENDPOINTS_"):
    if namespace and not key.startswith(namespace):
        key = namespace + key

    r = os.environ.get(key, default)
    return r


ENCODING = get("ENCODING", "UTF-8")

