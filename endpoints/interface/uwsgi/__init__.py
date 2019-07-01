# -*- coding: utf-8 -*-
from __future__ import unicode_literals, division, print_function, absolute_import

try:
    import uwsgi
except ImportError:
    uwsgi = None

from ...compat.environ import *
from ..wsgi import Application

