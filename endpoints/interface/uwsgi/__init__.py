# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import
import logging
import json

logger = logging.getLogger(__name__)

try:
    import uwsgi
except ImportError:
    uwsgi = None

from ...compat.environ import *
from ..wsgi import Application
from ...utils import String, ByteString, JSONEncoder

